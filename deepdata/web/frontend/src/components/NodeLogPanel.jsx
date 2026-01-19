import { useRef, useEffect } from 'react';

/**
 * Node Log Panel - shows logs for selected MCTS node.
 *
 * Appears on right side when user clicks a tree node.
 */
export function NodeLogPanel({
  nodeId,
  logs,     // [{ timestamp, level, message }]
  onClose,
}) {
  const scrollRef = useRef(null);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  // Level colors
  const levelColors = {
    info: 'text-gray-600',
    debug: 'text-gray-400',
    warning: 'text-yellow-600',
    error: 'text-red-600',
    success: 'text-green-600',
  };

  // Format timestamp
  const formatTime = (ts) => {
    if (!ts) return '';
    const date = new Date(ts);
    return date.toLocaleTimeString('en-US', { hour12: false });
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span className="font-medium text-gray-900">Node Logs</span>
          <span className="text-xs text-gray-400 font-mono">{nodeId?.slice(0, 8)}</span>
        </div>
        <button
          onClick={onClose}
          className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Logs */}
      <div ref={scrollRef} className="flex-1 overflow-auto p-3 font-mono text-xs">
        {(!logs || logs.length === 0) ? (
          <div className="text-gray-400 text-center py-8">
            No logs for this node yet
          </div>
        ) : (
          <div className="space-y-1">
            {logs.map((log, i) => (
              <div key={i} className="flex gap-2">
                <span className="text-gray-400 flex-shrink-0">
                  {formatTime(log.timestamp)}
                </span>
                <span className={`${levelColors[log.level] || levelColors.info}`}>
                  {log.message}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
