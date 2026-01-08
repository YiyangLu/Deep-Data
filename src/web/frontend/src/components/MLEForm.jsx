import { useState, useRef, useEffect } from 'react';
import { ClickToEditField } from './ClickToEditField';
import { PathListField } from './PathListField';

/**
 * MLE configuration form with clean UI.
 *
 * - Text fields: Click to edit (Goal, Task Description, Output Requirements)
 * - Path fields: List with + button (Data Paths, Output Paths)
 * - Load/Save: File upload/download (no server storage)
 */

const TIME_UNITS = [
  { value: 'min', label: 'min', multiplier: 1 },
  { value: 'hour', label: 'hour', multiplier: 60 },
  { value: 'day', label: 'day', multiplier: 1440 },
];

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

export function MLEForm({ onStart, onAutoFill, isAutoFilling }) {
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
  const [showTimerPopover, setShowTimerPopover] = useState(false);
  const [showConfigPopover, setShowConfigPopover] = useState(false);

  // Refs for click outside and file input
  const timerRef = useRef(null);
  const configRef = useRef(null);
  const fileInputRef = useRef(null);

  // Close popovers on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (timerRef.current && !timerRef.current.contains(e.target)) {
        setShowTimerPopover(false);
      }
      if (configRef.current && !configRef.current.contains(e.target)) {
        setShowConfigPopover(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

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
        // Apply config defaults
        if (result.config) {
          if (result.config.time) {
            // Parse time in minutes and convert to value + unit
            const mins = result.config.time;
            if (mins >= 1440 && mins % 1440 === 0) {
              setTimeValue(mins / 1440);
              setTimeUnit('day');
            } else if (mins >= 60 && mins % 60 === 0) {
              setTimeValue(mins / 60);
              setTimeUnit('hour');
            } else {
              setTimeValue(mins);
              setTimeUnit('min');
            }
          }
          if (result.config.workers) setWorkers(result.config.workers);
          if (result.config.model) setModel(result.config.model);
        }
      }
    }
  };

  // Compute time in minutes from value and unit
  const getTimeInMinutes = () => {
    const unit = TIME_UNITS.find(u => u.value === timeUnit);
    return timeValue * (unit?.multiplier || 60);
  };

  const handleStart = () => {
    if (isComplete && onStart) {
      onStart({
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
          time_limit: getTimeInMinutes() * 60,  // Convert minutes to seconds
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

        {/* Right: Timer, Config */}
        <div className="flex items-center gap-2">
          {/* Timer */}
          <div className="relative" ref={timerRef}>
            <button
              onClick={() => setShowTimerPopover(!showTimerPopover)}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-sm transition-colors text-gray-600 hover:text-green-700 hover:bg-green-50"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{timeValue}{timeUnit === 'min' ? 'm' : timeUnit === 'hour' ? 'h' : 'd'}</span>
            </button>

            {/* Timer popover */}
            {showTimerPopover && (
              <div className="absolute top-full right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg p-3 min-w-[160px] z-20">
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={timeValue}
                    onChange={(e) => setTimeValue(parseInt(e.target.value) || 1)}
                    className="w-16 px-2 py-1 text-sm border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-green-500"
                    min="1"
                  />
                  <div className="flex gap-1">
                    {TIME_UNITS.map((unit) => (
                      <button
                        key={unit.value}
                        onClick={() => setTimeUnit(unit.value)}
                        className={`px-2 py-1 text-xs rounded transition-colors ${
                          timeUnit === unit.value
                            ? 'bg-green-600 text-white'
                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }`}
                      >
                        {unit.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

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
