import { useState, useRef } from 'react';
import { PlotHistoryDropdown } from './PlotHistoryDropdown';
import { TimeSelector, timeToSeconds } from './TimeSelector';
import { CwdInput } from './CwdInput';

/**
 * Format token count for display (e.g., 1234 -> "1.2k")
 */
function formatTokens(count) {
  if (count >= 1000000) {
    return (count / 1000000).toFixed(1) + 'M';
  }
  if (count >= 1000) {
    return (count / 1000).toFixed(1) + 'k';
  }
  return count.toString();
}

/**
 * Message input box with send button and status bar.
 *
 * Supports Enter to send, Shift+Enter for new line.
 * Status bar shows plot history icon and token stats.
 */
export function InputBox({ onSend, onDeepPlot, disabled, isProcessing, sessionId, plotTabs, onRecoverPlot, stats, sessionType, isNewSession, cwdInfo, onCwdChange, currentCwd }) {
  const [input, setInput] = useState('');
  const [copied, setCopied] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState([]); // Array of { name, uploading, error }
  const [deepPlotTimeValue, setDeepPlotTimeValue] = useState(2); // Default 2 minutes
  const [deepPlotTimeUnit, setDeepPlotTimeUnit] = useState('min');
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  // Copy detailed token stats to clipboard
  const handleCopyStats = async () => {
    if (!stats) return;

    const lines = [];
    if (stats.usage?.input_tokens !== undefined) {
      lines.push(`Input tokens: ${stats.usage.input_tokens.toLocaleString()}`);
    }
    if (stats.usage?.output_tokens !== undefined) {
      lines.push(`Output tokens: ${stats.usage.output_tokens.toLocaleString()}`);
    }
    if (stats.usage?.input_tokens !== undefined && stats.usage?.output_tokens !== undefined) {
      lines.push(`Total tokens: ${(stats.usage.input_tokens + stats.usage.output_tokens).toLocaleString()}`);
    }
    if (stats.total_cost_usd !== undefined) {
      lines.push(`Cost: $${stats.total_cost_usd.toFixed(4)}`);
    }
    if (stats.duration_ms !== undefined) {
      lines.push(`Duration: ${(stats.duration_ms / 1000).toFixed(1)}s`);
    }
    if (stats.num_turns !== undefined) {
      lines.push(`Turns: ${stats.num_turns}`);
    }

    const text = lines.join('\n');
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // Determine placeholder text based on state
  const getPlaceholder = () => {
    if (isProcessing) {
      return "Agent is thinking...";
    }
    return "Ask anything";
  };

  const handleSend = () => {
    const trimmed = input.trim();
    if (disabled) return;

    // Deep Plot mode: triggered by files OR sessionType='deep_plot'
    if ((uploadedFiles.length > 0 || sessionType === 'deep_plot') && onDeepPlot) {
      // Deep Plot: call API with files and duration (prompt is optional, files can be empty)
      onDeepPlot({
        files: uploadedFiles.map(f => f.name),
        timeout: timeToSeconds(deepPlotTimeValue, deepPlotTimeUnit),
        prompt: trimmed
      });
      // Clear after starting
      setUploadedFiles([]);
      setInput('');
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    } else if (trimmed) {
      // Normal mode: send to WebSocket (requires input)
      onSend(trimmed);
      setInput('');
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e) => {
    // Enter without Shift sends the message
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e) => {
    setInput(e.target.value);

    // Auto-resize textarea
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
  };

  // Handle file selection (multiple files)
  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    // Add files with uploading state
    const newFiles = files.map(f => ({ name: f.name, uploading: true, error: null }));
    setUploadedFiles(prev => [...prev, ...newFiles]);

    // Upload each file
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        const formData = new FormData();
        formData.append('file', file);
        // Include cwd so file is uploaded to the correct directory
        if (cwdInfo?.cwd) {
          formData.append('cwd', cwdInfo.cwd);
        }

        const response = await fetch('/api/upload', {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          throw new Error(`Upload failed: ${response.statusText}`);
        }

        const result = await response.json();
        // Update the specific file's state
        setUploadedFiles(prev => prev.map(f =>
          f.name === file.name && f.uploading
            ? { name: result.filename || file.name, uploading: false, error: null }
            : f
        ));
      } catch (err) {
        setUploadedFiles(prev => prev.map(f =>
          f.name === file.name && f.uploading
            ? { name: file.name, uploading: false, error: err.message }
            : f
        ));
      }
    }

    // Reset file input so same files can be selected again
    e.target.value = '';
  };

  // Clear a specific uploaded file
  const handleClearFile = (fileName) => {
    setUploadedFiles(prev => prev.filter(f => f.name !== fileName));
  };

  // Clear all uploaded files
  const handleClearAllFiles = () => {
    setUploadedFiles([]);
  };

  return (
    <div className="p-4 pb-6">
      <div className="max-w-3xl mx-auto">
        {/* Status bar above input: left = plot history + cwd, right = token stats */}
        <div className="flex items-center justify-between mb-2 px-1 gap-2">
          {/* Left side: plot history and cwd - cwd disappears when no space */}
          <div className="flex items-center gap-3 min-w-0 flex-1 overflow-hidden">
            <div className="flex-shrink-0">
              <PlotHistoryDropdown sessionId={sessionId} plotTabs={plotTabs} onRecoverPlot={onRecoverPlot} />
            </div>
            <CwdInput isEditable={isNewSession} cwdInfo={cwdInfo} onCwdChange={onCwdChange} currentCwd={currentCwd} />
          </div>

          {/* Right side: token stats - clickable to copy, never shrink */}
          {stats && (
            <button
              onClick={handleCopyStats}
              className="flex items-center gap-3 text-xs text-gray-500 hover:text-gray-700 cursor-pointer transition-colors flex-shrink-0"
              title="Click to copy detailed stats"
            >
              {copied ? (
                <span className="text-green-600 font-medium">Copied!</span>
              ) : (
                <>
                  {(stats.usage?.input_tokens !== undefined || stats.usage?.output_tokens !== undefined) && (
                    <span>
                      <span className="text-blue-600">{stats.usage?.input_tokens !== undefined ? formatTokens(stats.usage.input_tokens) : '-'}</span>
                      <span className="mx-0.5">/</span>
                      <span className="text-green-600">{stats.usage?.output_tokens !== undefined ? formatTokens(stats.usage.output_tokens) : '-'}</span>
                      <span className="ml-0.5">tok</span>
                    </span>
                  )}
                  {stats.total_cost_usd !== undefined && (
                    <span>${stats.total_cost_usd.toFixed(4)}</span>
                  )}
                  {stats.duration_ms !== undefined && (
                    <span>{(stats.duration_ms / 1000).toFixed(1)}s</span>
                  )}
                </>
              )}
            </button>
          )}
        </div>

        <div className="bg-white border border-light-border rounded-2xl overflow-hidden focus-within:ring-1 focus-within:ring-gray-300">
          {/* Textarea area */}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={getPlaceholder()}
            disabled={disabled}
            rows={1}
            className="w-full px-4 pt-3 pb-1 text-light-text placeholder-gray-400 resize-none focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed bg-transparent"
            style={{ maxHeight: '200px' }}
          />
          {/* File chips - shown when files are uploaded */}
          {uploadedFiles.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 px-3 py-1 mx-2 mb-1">
              {uploadedFiles.map((file, index) => (
                <div key={`${file.name}-${index}`} className="flex items-center gap-1">
                  <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs ${
                    file.error
                      ? 'bg-red-100 text-red-700'
                      : file.uploading
                        ? 'bg-gray-100 text-gray-500'
                        : 'bg-blue-100 text-blue-700'
                  }`}>
                    {file.uploading ? (
                      <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                      </svg>
                    ) : (
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    )}
                    <span className="max-w-[150px] truncate">{file.name}</span>
                    <button
                      onClick={() => handleClearFile(file.name)}
                      className="ml-0.5 p-0.5 rounded-full hover:bg-blue-200 transition-colors"
                      title="Remove file"
                    >
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                  {file.error && (
                    <span className="text-xs text-red-600">{file.error}</span>
                  )}
                </div>
              ))}
              {/* Clear all button when multiple files */}
              {uploadedFiles.length > 1 && (
                <button
                  onClick={handleClearAllFiles}
                  className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-full transition-colors"
                  title="Clear all files"
                >
                  Clear all
                </button>
              )}
            </div>
          )}

          {/* Bottom bar with file upload and send button */}
          <div className="flex justify-between items-center px-2 pb-2">
            {/* Left side: + button for file upload */}
            <div className="flex items-center gap-1">
              {/* Hidden file input - supports multiple files */}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleFileSelect}
                className="hidden"
                accept=".csv,.json,.xlsx,.xls,.parquet,.txt,.tsv,.md"
              />

              {/* + File upload button */}
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled || uploadedFiles.some(f => f.uploading)}
                className="p-2 rounded-full text-gray-500 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title="Upload file(s)"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                </svg>
              </button>

              {/* Deep Plot indicator - shown in deep_plot mode or when files uploaded */}
              {(sessionType === 'deep_plot' || uploadedFiles.length > 0) && (
                <div className="flex items-center gap-1 px-2 py-1 bg-purple-100 rounded-full">
                  <svg className="w-3.5 h-3.5 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  <span className="text-purple-700 text-sm font-medium">Deep Plot</span>
                  <div className="w-px h-4 bg-purple-300 mx-1"></div>
                  <TimeSelector
                    value={deepPlotTimeValue}
                    unit={deepPlotTimeUnit}
                    onChange={(val, unit) => {
                      setDeepPlotTimeValue(val);
                      setDeepPlotTimeUnit(unit);
                    }}
                    theme="purple"
                  />
                </div>
              )}
            </div>

            {/* Send button */}
            <button
              onClick={handleSend}
              disabled={disabled || (uploadedFiles.length === 0 && !input.trim())}
              className="p-2 rounded-full bg-black hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
              title={uploadedFiles.length > 0 ? 'Start Deep Plot analysis' : 'Send message'}
            >
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
