import { useState } from 'react';

/**
 * MLE Status Bar - bottom bar showing run status.
 *
 * Displays: workers, best score, steps progress, elapsed time.
 * Buttons change based on status:
 * - running: [Pause]
 * - paused/completed: [Resume] (continue search with more time/steps)
 * - error: (no actions)
 */
export function MLEStatusBar({
  status,          // 'running' | 'paused' | 'completed' | 'error' | 'starting'
  workers,
  totalWorkers,
  bestScore,
  steps,
  maxSteps,
  elapsed,
  error,           // Error message when status is 'error'
  cwd,             // Working directory
  onPause,
  onResume,
}) {
  const [showResumeModal, setShowResumeModal] = useState(false);
  const [additionalTime, setAdditionalTime] = useState(60); // minutes
  const [additionalSteps, setAdditionalSteps] = useState(50);

  // Format elapsed time (seconds -> "1h 23m" or "5m 30s")
  const formatTime = (seconds) => {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    if (mins < 60) return `${mins}m ${seconds % 60}s`;
    const hours = Math.floor(mins / 60);
    return `${hours}h ${mins % 60}m`;
  };

  // Format score (handle null/undefined)
  const formatScore = (score) => {
    if (score === null || score === undefined) return '—';
    return score.toFixed(4);
  };

  const handleResumeClick = () => {
    setShowResumeModal(true);
  };

  const handleResumeConfirm = () => {
    onResume?.(additionalTime * 60, additionalSteps); // Convert minutes to seconds
    setShowResumeModal(false);
  };

  const isRunning = status === 'running' || status === 'starting';
  const canResume = status === 'paused' || status === 'completed';

  return (
    <>
      <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-t border-gray-200 text-sm">
        {/* Left: Status metrics */}
        <div className="flex items-center gap-6">
          {/* Status indicator */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${
              isRunning ? 'bg-green-500 animate-pulse' :
              status === 'paused' ? 'bg-yellow-500' :
              status === 'completed' ? 'bg-blue-500' :
              'bg-red-500'
            }`} />
            <span className="text-gray-600 capitalize">{status}</span>
            {/* Error message */}
            {status === 'error' && error && (
              <span className="text-red-600 text-xs ml-2 truncate max-w-48" title={error}>
                ({error})
              </span>
            )}
          </div>

          {/* Workers */}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              {[...Array(totalWorkers)].map((_, i) => (
                <div
                  key={i}
                  className={`w-2 h-2 rounded-full ${
                    i < workers ? 'bg-green-500' : 'bg-gray-300'
                  }`}
                />
              ))}
            </div>
            <span className="text-gray-600">
              Workers: {workers}/{totalWorkers}
            </span>
          </div>

          {/* Best Score */}
          <div className="flex items-center gap-1.5">
            <svg className="w-4 h-4 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
            </svg>
            <span className="text-gray-600">Best:</span>
            <span className="font-mono font-medium text-gray-900">{formatScore(bestScore)}</span>
          </div>

          {/* Steps */}
          <span className="text-gray-600">
            Steps: {steps}
          </span>

          {/* Elapsed Time */}
          <div className="flex items-center gap-1.5">
            <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-gray-600">{formatTime(elapsed)}</span>
          </div>

          {/* Working Directory */}
          {cwd && (
            <div className="flex items-center gap-1.5" title={cwd}>
              <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              <span className="text-gray-600 truncate max-w-[200px]">
                {'.../' + cwd.split('/').slice(-2).join('/')}
              </span>
            </div>
          )}
        </div>

        {/* Right: Action buttons */}
        <div className="flex items-center gap-2">
          {/* Pause button - shown when running */}
          {isRunning && (
            <button
              onClick={onPause}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-yellow-700 bg-yellow-50 hover:bg-yellow-100 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Pause
            </button>
          )}

          {/* Resume button - shown when paused or completed */}
          {canResume && (
            <button
              onClick={handleResumeClick}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-green-700 bg-green-50 hover:bg-green-100 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Resume
            </button>
          )}
        </div>
      </div>

      {/* Resume Modal */}
      {showResumeModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-96">
            <h3 className="text-lg font-semibold mb-4">Resume Search</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Additional Time (minutes)
                </label>
                <input
                  type="number"
                  value={additionalTime}
                  onChange={(e) => setAdditionalTime(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  min="1"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Additional Steps
                </label>
                <input
                  type="number"
                  value={additionalSteps}
                  onChange={(e) => setAdditionalSteps(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  min="1"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowResumeModal(false)}
                className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleResumeConfirm}
                className="px-4 py-2 text-sm text-white bg-green-600 hover:bg-green-700 rounded-lg transition-colors"
              >
                Resume Search
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
