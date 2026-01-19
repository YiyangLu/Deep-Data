import { useState, useEffect, useRef } from 'react';

/**
 * Session history dropdown component.
 *
 * Shows a dropdown with recent sessions and MLE runs when history icon is clicked.
 * Allows switching between sessions and resuming MLE runs.
 */
export function SessionHistoryDropdown({ currentSessionId, onSessionSwitch, onMleResume }) {
  const [isOpen, setIsOpen] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [mleActivities, setMleActivities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, right: 0 });
  const dropdownRef = useRef(null);
  const buttonRef = useRef(null);

  // Load sessions and MLE activities when opened
  useEffect(() => {
    if (isOpen) {
      setLoading(true);

      // Fetch both sessions and MLE activities in parallel
      Promise.all([
        fetch('/api/sessions/list').then(r => r.json()),
        fetch('/api/activities?activity_type=mle&limit=20').then(r => r.json())
      ])
        .then(([sessionsData, activitiesData]) => {
          setSessions(sessionsData.sessions || []);
          setMleActivities(activitiesData.activities || []);
          setLoading(false);
        })
        .catch(err => {
          console.error('Failed to load history:', err);
          setLoading(false);
        });
    }
  }, [isOpen]);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const formatTimeAgo = (timestamp) => {
    const now = new Date();
    const then = new Date(timestamp);
    const diffMs = now - then;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)} hours ago`;

    // Yesterday
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (then.toDateString() === yesterday.toDateString()) {
      return 'Yesterday';
    }

    // Older
    const days = Math.floor(diffMins / 1440);
    return `${days} days ago`;
  };

  const shortenCwd = (cwd) => {
    const parts = cwd.split('/');
    if (parts.length > 3) {
      return `.../${parts.slice(-2).join('/')}`;
    }
    return cwd;
  };

  const truncateQuery = (query, maxLen = 60) => {
    if (query.length <= maxLen) return query;
    return query.substring(0, maxLen) + '...';
  };

  const handleButtonClick = () => {
    if (!isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPosition({
        top: rect.bottom + 8, // 8px = mt-2
        right: window.innerWidth - rect.right
      });
    }
    setIsOpen(!isOpen);
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* History Icon Button */}
      <button
        ref={buttonRef}
        onClick={handleButtonClick}
        className="py-2.5 px-2 hover:bg-gray-100 rounded-lg transition-colors border-b-2 border-b-transparent"
        title="Session History"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div
          className="fixed w-[450px] bg-white rounded-lg shadow-xl border border-gray-200 z-50"
          style={{ top: `${dropdownPosition.top}px`, right: `${dropdownPosition.right}px` }}
        >
          {/* Header */}
          <div className="px-4 py-3 border-b border-gray-200 flex justify-between items-center">
            <h3 className="text-sm font-semibold text-gray-900">Resume Session</h3>
            <button
              onClick={() => setIsOpen(false)}
              className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            >
              ×
            </button>
          </div>

          {/* Session List */}
          <div className="max-h-[500px] overflow-y-auto">
            {loading ? (
              <div className="px-4 py-8 text-center text-gray-500">
                Loading history...
              </div>
            ) : (
              <>
                {/* MLE Runs Section */}
                {mleActivities.length > 0 && (
                  <>
                    <div className="px-4 py-2 bg-gray-50 border-b border-gray-200">
                      <span className="text-xs font-semibold text-gray-600 uppercase tracking-wider">
                        MLE Runs
                      </span>
                    </div>
                    {mleActivities.map((activity) => {
                      const statusColor = {
                        running: 'text-green-600 bg-green-100',
                        paused: 'text-yellow-600 bg-yellow-100',
                        completed: 'text-blue-600 bg-blue-100',
                        failed: 'text-red-600 bg-red-100',
                      }[activity.status] || 'text-gray-600 bg-gray-100';

                      return (
                        <button
                          key={activity.id}
                          onClick={() => {
                            if (onMleResume) {
                              onMleResume(activity);
                              setIsOpen(false);
                            }
                          }}
                          className="w-full px-4 py-3 text-left transition-colors hover:bg-gray-50 cursor-pointer"
                        >
                          <div className="flex items-start gap-2">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium text-gray-900 truncate">
                                  {activity.name}
                                </span>
                                <span className={`text-xs px-1.5 py-0.5 rounded ${statusColor}`}>
                                  {activity.status}
                                </span>
                              </div>
                              <div className="text-xs text-gray-500 mt-1">
                                {formatTimeAgo(activity.updated_at)}
                                {activity.config?.goal && (
                                  <> · {truncateQuery(activity.config.goal, 40)}</>
                                )}
                              </div>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </>
                )}

                {/* Sessions Section */}
                {sessions.length > 0 && (
                  <>
                    <div className="px-4 py-2 bg-gray-50 border-b border-gray-200">
                      <span className="text-xs font-semibold text-gray-600 uppercase tracking-wider">
                        Chat Sessions
                      </span>
                    </div>
                    {sessions.map((session, idx) => {
                      const isCurrent = session.id === currentSessionId;

                      return (
                        <div key={session.id}>
                          {/* Separator after current session */}
                          {idx === 1 && (
                            <div className="border-t border-gray-200 my-2" />
                          )}

                          <button
                            onClick={() => {
                              if (!isCurrent) {
                                onSessionSwitch(session.id, session.session_name);
                                setIsOpen(false);
                              }
                            }}
                            className={`
                              w-full px-4 py-3 text-left transition-colors
                              ${isCurrent
                                ? 'bg-blue-50 cursor-default'
                                : 'hover:bg-gray-50 cursor-pointer'
                              }
                            `}
                          >
                            {/* Session info */}
                            <div className="flex items-start gap-2">
                              {isCurrent && (
                                <span className="text-blue-600 mt-0.5">❯</span>
                              )}
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className={`text-sm font-medium ${
                                    isCurrent ? 'text-blue-900' : 'text-gray-900'
                                  }`}>
                                    {session.session_name || 'Agent'}
                                  </span>
                                  <span className="text-xs text-gray-400">·</span>
                                  <span className={`text-sm truncate ${
                                    isCurrent ? 'text-blue-700' : 'text-gray-600'
                                  }`}>
                                    {truncateQuery(session.query, 40)}
                                  </span>
                                </div>
                                <div className="text-xs text-gray-500 mt-1">
                                  {formatTimeAgo(session.updated_at)}
                                  {' · '}
                                  {session.message_count} messages
                                  {' · '}
                                  {shortenCwd(session.cwd)}
                                </div>
                              </div>
                            </div>
                          </button>
                        </div>
                      );
                    })}
                  </>
                )}

                {/* Empty state */}
                {sessions.length === 0 && mleActivities.length === 0 && (
                  <div className="px-4 py-8 text-center text-gray-500">
                    No previous sessions or runs
                  </div>
                )}
              </>
            )}
          </div>

        </div>
      )}
    </div>
  );
}
