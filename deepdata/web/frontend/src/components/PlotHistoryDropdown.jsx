import { useState, useEffect, useRef } from 'react';

/**
 * Plot history dropdown component.
 *
 * Shows a dropdown with all plots for the current session.
 * Fetches from backend to show ALL plots (including closed ones).
 * Click to recover/activate a plot.
 */
export function PlotHistoryDropdown({ sessionId, plotTabs, onRecoverPlot }) {
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ bottom: 0, left: 0 });
  const [allPlots, setAllPlots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fetchedSessionName, setFetchedSessionName] = useState(null);
  const dropdownRef = useRef(null);
  const buttonRef = useRef(null);

  // Check which plots are currently open as tabs
  const openPlotIds = new Set(
    (plotTabs || [])
      .filter(tab => tab.session_id === sessionId)
      .map(tab => tab.plot_id)
  );

  // Fetch all plots for session when dropdown opens
  useEffect(() => {
    if (isOpen && sessionId) {
      setLoading(true);
      fetch(`/api/plots/${sessionId}`)
        .then(res => res.json())
        .then(data => {
          setAllPlots(data.plots || []);
          // Store session_name from backend (authoritative source)
          setFetchedSessionName(data.session_name || null);
          setLoading(false);
        })
        .catch(err => {
          console.error('Failed to fetch plots:', err);
          setAllPlots([]);
          setFetchedSessionName(null);
          setLoading(false);
        });
    }
  }, [isOpen, sessionId]);

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

  const handleButtonClick = () => {
    if (!isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPosition({
        bottom: window.innerHeight - rect.top + 8,
        left: rect.left
      });
    }
    setIsOpen(!isOpen);
  };

  const handleItemClick = (plot) => {
    const isOpen = openPlotIds.has(plot.plot_id);

    if (onRecoverPlot) {
      onRecoverPlot({
        plot_id: plot.plot_id,
        session_id: sessionId,
        session_name: fetchedSessionName,  // From backend API (authoritative)
        plot_url: `/plot/${sessionId}/${plot.plot_id}`,
        isAlreadyOpen: isOpen
      });
    }
    setIsOpen(false);
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Chart Icon Button */}
      <button
        ref={buttonRef}
        onClick={handleButtonClick}
        className="p-1.5 hover:bg-gray-100 rounded transition-colors text-gray-500 hover:text-gray-700"
        title="Plot History"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div
          className="fixed w-[250px] bg-white rounded-lg shadow-xl border border-gray-200 z-50"
          style={{ bottom: `${dropdownPosition.bottom}px`, left: `${dropdownPosition.left}px` }}
        >
          {/* Header */}
          <div className="px-3 py-2 border-b border-gray-200 flex justify-between items-center">
            <h3 className="text-sm font-semibold text-gray-900">Session Plots</h3>
            <button
              onClick={() => setIsOpen(false)}
              className="text-gray-400 hover:text-gray-600 text-lg leading-none"
            >
              ×
            </button>
          </div>

          {/* Plot List */}
          <div className="max-h-[300px] overflow-y-auto">
            {loading ? (
              <div className="px-3 py-4 text-center text-gray-500 text-sm">
                Loading...
              </div>
            ) : allPlots.length === 0 ? (
              <div className="px-3 py-4 text-center text-gray-500 text-sm">
                No plots in this session
              </div>
            ) : (
              allPlots.map((plot) => {
                const isOpenTab = openPlotIds.has(plot.plot_id);
                return (
                  <button
                    key={`${sessionId}-${plot.plot_id}`}
                    onClick={() => handleItemClick(plot)}
                    disabled={!plot.has_data}
                    className={`w-full px-3 py-2 text-left transition-colors flex items-center justify-between
                      ${plot.has_data ? 'hover:bg-gray-50' : 'opacity-50 cursor-not-allowed'}
                    `}
                  >
                    <div>
                      <div className="text-sm text-gray-900">
                        {plot.plot_id}
                      </div>
                      {plot.description && (
                        <div className="text-xs text-gray-500 truncate max-w-[180px]">
                          {plot.description}
                        </div>
                      )}
                    </div>
                    {isOpenTab && (
                      <span className="text-xs text-green-600 bg-green-50 px-1.5 py-0.5 rounded">
                        open
                      </span>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
