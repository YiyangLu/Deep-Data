import { useState, useRef, useEffect } from 'react';
import { ClickToEditField } from './ClickToEditField';
import { PathListField } from './PathListField';
import { TimeSelector, timeToSeconds, minutesToTime } from './TimeSelector';

/**
 * MLE configuration form with clean UI.
 *
 * - Text fields: Click to edit (Goal, Task Description, Output Requirements)
 * - Path fields: List with + button (Data Paths, Output Paths)
 * - Load/Save: File upload/download (no server storage)
 */

const WORKER_OPTIONS = [1, 2, 3, 4];

const MODEL_OPTIONS = [
  { value: 'haiku', label: 'Haiku' },
  { value: 'sonnet', label: 'Sonnet' },
  { value: 'opus', label: 'Opus' },
];

const MAX_STEPS_OPTIONS = [
  { value: 100, label: '100' },
  { value: 500, label: '500' },
  { value: Infinity, label: '∞' },
];

export function MLEForm({ onStart, onAutoFill, isAutoFilling, defaultWorkspace }) {
  // Workspace (editable before start)
  const [workspace, setWorkspace] = useState(defaultWorkspace || '');
  const [isEditingWorkspace, setIsEditingWorkspace] = useState(false);
  const [workspaceEditValue, setWorkspaceEditValue] = useState('');
  const [workspaceValidation, setWorkspaceValidation] = useState(null); // null | 'validating' | 'valid' | 'error'
  const [workspaceError, setWorkspaceError] = useState('');
  const workspaceInputRef = useRef(null);

  // Text fields
  const [goal, setGoal] = useState('');
  const [taskDescription, setTaskDescription] = useState('');
  const [outputRequirements, setOutputRequirements] = useState('');

  // Path fields (objects)
  const [dataPaths, setDataPaths] = useState({});
  const [outputPaths, setOutputPaths] = useState({});

  // Git worktree config (list of strings) - start empty like Goal
  const [gitignore, setGitignore] = useState([]);
  const [sync, setSync] = useState([]);

  // Config state (defaults match MCTSConfig)
  const [timeValue, setTimeValue] = useState(6);  // 6 hours
  const [timeUnit, setTimeUnit] = useState('hour');
  const [workers, setWorkers] = useState(2);  // Match num_gpus default
  const [model, setModel] = useState('opus');
  const [maxSteps, setMaxSteps] = useState(Infinity);

  // Custom input mode for config options
  const [customWorkers, setCustomWorkers] = useState(false);
  const [customMaxSteps, setCustomMaxSteps] = useState(false);

  // Popover state
  const [showConfigPopover, setShowConfigPopover] = useState(false);

  // Refs for click outside and file input
  const configRef = useRef(null);
  const workspaceRef = useRef(null);
  const fileInputRef = useRef(null);

  // Update workspace when defaultWorkspace changes
  useEffect(() => {
    if (defaultWorkspace && !workspace) {
      setWorkspace(defaultWorkspace);
    }
  }, [defaultWorkspace]);

  // Focus workspace input when editing
  useEffect(() => {
    if (isEditingWorkspace && workspaceInputRef.current) {
      workspaceInputRef.current.focus();
      workspaceInputRef.current.select();
    }
  }, [isEditingWorkspace]);

  // Close popovers on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (configRef.current && !configRef.current.contains(e.target)) {
        setShowConfigPopover(false);
      }
      if (workspaceRef.current && !workspaceRef.current.contains(e.target)) {
        if (isEditingWorkspace && workspaceValidation !== 'error') {
          handleWorkspaceCancel();
        }
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isEditingWorkspace, workspaceValidation]);

  // Workspace editing handlers
  const handleWorkspaceStartEdit = () => {
    setIsEditingWorkspace(true);
    setWorkspaceEditValue(workspace);
    setWorkspaceValidation(null);
    setWorkspaceError('');
  };

  const handleWorkspaceValidate = async (value) => {
    const trimmed = value.trim();
    if (!trimmed) {
      setWorkspaceValidation('error');
      setWorkspaceError('Path cannot be empty');
      return false;
    }

    setWorkspaceValidation('validating');

    try {
      const res = await fetch('/api/validate-cwd', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: trimmed })
      });
      const data = await res.json();

      if (data.valid) {
        setWorkspaceValidation('valid');
        setWorkspaceError('');
        setWorkspace(data.resolved_path);
        return true;
      } else {
        setWorkspaceValidation('error');
        setWorkspaceError(data.error || 'Invalid path');
        return false;
      }
    } catch (err) {
      setWorkspaceValidation('error');
      setWorkspaceError('Failed to validate path');
      return false;
    }
  };

  const handleWorkspaceConfirm = async () => {
    const isValid = await handleWorkspaceValidate(workspaceEditValue);
    if (isValid) {
      setIsEditingWorkspace(false);
    }
  };

  const handleWorkspaceCancel = () => {
    setIsEditingWorkspace(false);
    setWorkspaceEditValue(workspace);
    setWorkspaceValidation(null);
    setWorkspaceError('');
  };

  const handleWorkspaceKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleWorkspaceConfirm();
    } else if (e.key === 'Escape') {
      handleWorkspaceCancel();
    }
  };

  // Shorten workspace path for display
  const shortenPath = (path) => {
    if (!path) return '';
    const segments = path.split('/').filter(Boolean);
    return segments.length > 3
      ? '.../' + segments.slice(-2).join('/')
      : path;
  };

  // Load context from uploaded JSON file
  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const t = JSON.parse(event.target.result);
        // Fill form fields
        if (t.goal) setGoal(t.goal);
        if (t.task_description) setTaskDescription(t.task_description);
        if (t.data_paths) setDataPaths(t.data_paths);
        if (t.output_paths) setOutputPaths(t.output_paths);
        if (t.output_requirements) setOutputRequirements(t.output_requirements);
        if (t.gitignore) setGitignore(t.gitignore);
        if (t.sync) setSync(t.sync);
      } catch (err) {
        console.error('Failed to parse JSON:', err);
        alert('Invalid JSON file');
      }
    };
    reader.readAsText(file);
    // Reset input so same file can be loaded again
    e.target.value = '';
  };

  // Save context as JSON file download
  const handleSave = () => {
    const context = {
      goal,
      task_description: taskDescription,
      data_paths: dataPaths,
      output_paths: outputPaths,
      output_requirements: outputRequirements,
      gitignore,
      sync,
    };
    const blob = new Blob([JSON.stringify(context, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'mle-context.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Ready to start when goal is filled
  const isComplete = goal.trim().length > 0;

  const handleAutoFill = async () => {
    if (onAutoFill) {
      // Build partial context from current form state
      const partialContext = {};
      if (goal.trim()) partialContext.goal = goal;
      if (taskDescription.trim()) partialContext.task_description = taskDescription;
      if (Object.keys(dataPaths).length > 0) partialContext.data_paths = dataPaths;
      if (Object.keys(outputPaths).length > 0) partialContext.output_paths = outputPaths;
      if (outputRequirements.trim()) partialContext.output_requirements = outputRequirements;
      if (gitignore.length > 0) partialContext.gitignore = gitignore;
      if (sync.length > 0) partialContext.sync = sync;

      const result = await onAutoFill({
        partial_context: Object.keys(partialContext).length > 0 ? partialContext : null,
        model: model,  // Use selected model for discovery
      });
      if (result) {
        // Fill form fields from discovered context
        if (result.context) {
          if (result.context.goal) setGoal(result.context.goal);
          if (result.context.task_description) setTaskDescription(result.context.task_description);
          if (result.context.data_paths) setDataPaths(result.context.data_paths);
          if (result.context.output_paths) setOutputPaths(result.context.output_paths);
          if (result.context.output_requirements) setOutputRequirements(result.context.output_requirements);
        }
        // Fill git worktree config
        if (result.git_worktree) {
          if (result.git_worktree.gitignore) setGitignore(result.git_worktree.gitignore);
          if (result.git_worktree.sync) setSync(result.git_worktree.sync);
        }
        // Note: Auto-fill does not touch config (time, workers, model)
      }
    }
  };

  const handleStart = () => {
    if (isComplete && onStart) {
      onStart({
        workspace,  // Include workspace path
        context: {
          goal,
          task_description: taskDescription,
          data_paths: dataPaths,
          output_paths: outputPaths,
          output_requirements: outputRequirements,
        },
        git_worktree: {
          gitignore,
          sync,
        },
        config: {
          time_limit: timeToSeconds(timeValue, timeUnit),
          parallel_workers: workers,
          model,
          max_steps: maxSteps === Infinity ? 0 : maxSteps,  // 0 = infinite
        },
      });
    }
  };

  return (
    <div className="w-full max-w-2xl">
      {/* Header - minimal */}
      <div className="flex items-center justify-between mb-6">
        {/* Left: Title */}
        <span className="text-lg font-medium text-gray-900">MLE Run</span>

        {/* Right: Workspace, Timer, Config */}
        <div className="flex items-center gap-2">
          {/* Workspace */}
          <div className="relative" ref={workspaceRef}>
            {isEditingWorkspace ? (
              <div className="flex items-center gap-1.5">
                <input
                  ref={workspaceInputRef}
                  type="text"
                  value={workspaceEditValue}
                  onChange={(e) => {
                    setWorkspaceEditValue(e.target.value);
                    setWorkspaceValidation(null);
                    setWorkspaceError('');
                  }}
                  onKeyDown={handleWorkspaceKeyDown}
                  className={`w-48 px-2 py-1 text-xs border rounded focus:outline-none focus:ring-1 ${
                    workspaceValidation === 'error'
                      ? 'border-red-300 focus:ring-red-300 bg-red-50'
                      : 'border-gray-300 focus:ring-green-300'
                  }`}
                  placeholder="Enter workspace path"
                />
                {workspaceValidation === 'validating' && (
                  <svg className="w-3 h-3 animate-spin text-gray-400" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                )}
                {workspaceValidation === 'valid' && (
                  <svg className="w-3 h-3 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
                {workspaceValidation === 'error' && (
                  <svg className="w-3 h-3 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                )}
                <button
                  onClick={handleWorkspaceConfirm}
                  disabled={workspaceValidation === 'validating'}
                  className="px-2 py-1 text-xs text-white bg-green-500 hover:bg-green-600 rounded disabled:opacity-50"
                >
                  OK
                </button>
                <button
                  onClick={handleWorkspaceCancel}
                  className="text-xs text-gray-500 hover:text-gray-700"
                >
                  Cancel
                </button>
                {workspaceValidation === 'error' && workspaceError && (
                  <div className="absolute top-full left-0 mt-1 px-2 py-1.5 text-xs text-red-700 bg-red-100 border border-red-300 rounded shadow-md whitespace-nowrap z-30">
                    <span className="font-medium">Error:</span> {workspaceError}
                  </div>
                )}
              </div>
            ) : (
              <button
                onClick={handleWorkspaceStartEdit}
                className="flex items-center gap-1 px-2 py-1 rounded-md text-sm transition-colors text-gray-600 hover:text-green-700 hover:bg-green-50"
                title={workspace || 'Set workspace'}
              >
                <span className="text-xs truncate max-w-[150px]">
                  {workspace ? shortenPath(workspace) : 'Set workspace'}
                </span>
                <svg className="w-2.5 h-2.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                </svg>
              </button>
            )}
          </div>

          {/* Timer */}
          <TimeSelector
            value={timeValue}
            unit={timeUnit}
            onChange={(val, unit) => {
              setTimeValue(val);
              setTimeUnit(unit);
            }}
            theme="green"
            dropdownPosition="bottom"
          />

          {/* Config */}
          <div className="relative" ref={configRef}>
            <button
              onClick={() => setShowConfigPopover(!showConfigPopover)}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-sm transition-colors text-gray-600 hover:text-green-700 hover:bg-green-50"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>

            {/* Config popover */}
            {showConfigPopover && (
              <div className="absolute top-full right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg p-3 min-w-[200px] z-20">
                {/* Workers */}
                <div className="mb-3">
                  <label className="block text-xs text-gray-500 mb-1">Workers</label>
                  <div className="flex gap-1">
                    {WORKER_OPTIONS.map((w) => (
                      <button
                        key={w}
                        onClick={() => { setWorkers(w); setCustomWorkers(false); }}
                        className={`flex-1 px-2 py-1 text-sm rounded transition-colors ${
                          workers === w && !customWorkers
                            ? 'bg-green-600 text-white'
                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }`}
                      >
                        {w}
                      </button>
                    ))}
                    {customWorkers ? (
                      <input
                        type="number"
                        value={workers}
                        onChange={(e) => setWorkers(parseInt(e.target.value) || 1)}
                        className="w-14 px-2 py-1 text-sm border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-green-500"
                        min="1"
                        autoFocus
                      />
                    ) : (
                      <button
                        onClick={() => setCustomWorkers(true)}
                        className="px-2 py-1 text-sm rounded bg-gray-100 text-gray-500 hover:bg-gray-200 transition-colors"
                      >
                        ...
                      </button>
                    )}
                  </div>
                </div>

                {/* Model */}
                <div className="mb-3">
                  <label className="block text-xs text-gray-500 mb-1">Model</label>
                  <div className="flex gap-1">
                    {MODEL_OPTIONS.map((m) => (
                      <button
                        key={m.value}
                        onClick={() => setModel(m.value)}
                        className={`flex-1 px-2 py-1 text-sm rounded transition-colors ${
                          model === m.value
                            ? 'bg-green-600 text-white'
                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }`}
                      >
                        {m.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Max Steps */}
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Max Steps</label>
                  <div className="flex gap-1">
                    {MAX_STEPS_OPTIONS.map((opt) => (
                      <button
                        key={opt.label}
                        onClick={() => { setMaxSteps(opt.value); setCustomMaxSteps(false); }}
                        className={`flex-1 px-2 py-1 text-sm rounded transition-colors ${
                          maxSteps === opt.value && !customMaxSteps
                            ? 'bg-green-600 text-white'
                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                    {customMaxSteps ? (
                      <input
                        type="number"
                        value={maxSteps === Infinity ? '' : maxSteps}
                        onChange={(e) => setMaxSteps(parseInt(e.target.value) || 1)}
                        className="w-14 px-2 py-1 text-sm border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-green-500"
                        min="1"
                        autoFocus
                        placeholder="N"
                      />
                    ) : (
                      <button
                        onClick={() => setCustomMaxSteps(true)}
                        className="px-2 py-1 text-sm rounded bg-gray-100 text-gray-500 hover:bg-gray-200 transition-colors"
                      >
                        ...
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Body - Form fields */}
      <div className="space-y-6">
        {/* Goal */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-2">Goal</label>
          <ClickToEditField
            label="Goal"
            value={goal}
            onChange={setGoal}
            placeholder="High-level objective (e.g., Maximize ROC-AUC)"
            maxPreviewLength={60}
          />
        </div>

        {/* Task Description */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-2">Task Description</label>
          <ClickToEditField
            label="Task Description"
            value={taskDescription}
            onChange={setTaskDescription}
            placeholder="What the ML task is about..."
            maxPreviewLength={80}
            multiline
          />
        </div>

        {/* Data Paths */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-2">Data Paths</label>
          <PathListField
            paths={dataPaths}
            onChange={setDataPaths}
            examples={[
              { key: 'train', path: 'data/train.csv' },
              { key: 'test', path: 'data/test.csv' }
            ]}
          />
        </div>

        {/* Output Paths */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-2">Output Paths</label>
          <PathListField
            paths={outputPaths}
            onChange={setOutputPaths}
            examples={[
              { key: 'prediction', path: 'output/pred.csv' },
              { key: 'model', path: 'model/model.pkl' }
            ]}
          />
        </div>

        {/* Output Requirements */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-2">Output Requirements</label>
          <ClickToEditField
            label="Output Requirements"
            value={outputRequirements}
            onChange={setOutputRequirements}
            placeholder="Format requirements for output files..."
            maxPreviewLength={80}
            multiline
          />
        </div>

        {/* Git Worktree Config Section */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-2">Git Worktree Config</label>
          <div className="space-y-4 pl-4">
            {/* gitignore */}
            <div>
              <label className="block text-xs text-gray-400 mb-1">gitignore</label>
              <ClickToEditField
                label="gitignore"
                value={gitignore.join('\n')}
                onChange={(val) => setGitignore(val.split('\n').filter(line => line.trim()))}
                placeholder="Patterns to ignore (one per line): data/ output/"
                multiline
              />
            </div>

            {/* sync */}
            <div>
              <label className="block text-xs text-gray-400 mb-1">sync</label>
              <ClickToEditField
                label="sync"
                value={sync.join('\n')}
                onChange={(val) => setSync(val.split('\n').filter(line => line.trim()))}
                placeholder="Paths to sync (one per line): data/"
                multiline
              />
            </div>
          </div>
        </div>
      </div>

      {/* Footer - Actions */}
      <div className="flex items-center justify-between mt-8">
        {/* Left: Load/Save (file-based) */}
        <div className="flex items-center gap-2">
          {/* Hidden file input for Load */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            onChange={handleFileUpload}
            className="hidden"
          />

          {/* Load button - triggers file picker */}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            <span>Load</span>
          </button>

          {/* Save button - downloads JSON */}
          <button
            onClick={handleSave}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            <span>Save</span>
          </button>
        </div>

        {/* Right: Auto-fill/Start */}
        <div className="flex items-center gap-2">
          {/* Auto-fill button */}
          <button
            onClick={handleAutoFill}
            disabled={isAutoFilling}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
          >
            {isAutoFilling ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                </svg>
                <span>Discovering...</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <span>Auto-fill</span>
              </>
            )}
          </button>

          {/* Start button */}
          <button
            onClick={handleStart}
            disabled={!isComplete}
            className="flex items-center gap-1.5 px-4 py-1.5 text-sm text-white bg-green-600 hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
            <span>Start</span>
          </button>
        </div>
      </div>
    </div>
  );
}
