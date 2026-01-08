import { useState, useRef, useEffect } from 'react';
import { TabBarButtons } from './TabBarButtons';

/**
 * Tab strip for managing multiple plot tabs.
 *
 * Plot tabs store session_name directly (from plot_show events).
 * No lookup from agent tabs needed - follows TAB_SESSION_ARCHITECTURE.md.
 */
export function PlotTabs({
  tabs,
  activeTabIndex,
  onTabClick,
  onTabClose,
  showButtons,
  onNewTab,
  currentSessionId,
  onSessionSwitch
}) {
  const [hoveredTabIndex, setHoveredTabIndex] = useState(null);
  const tabStripRef = useRef(null);

  // Scroll active tab into view
  useEffect(() => {
    if (tabStripRef.current && activeTabIndex !== null) {
      const activeTab = tabStripRef.current.children[activeTabIndex];
      if (activeTab) {
        activeTab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
      }
    }
  }, [activeTabIndex]);

  if (tabs.length === 0) {
    return null;
  }

  return (
    <div className="flex items-center border-b border-gray-200 bg-white overflow-x-auto overflow-y-hidden">
      <div ref={tabStripRef} className="flex items-center min-w-0">
        {tabs.map((tab, index) => {
          const isActive = index === activeTabIndex;
          const isHovered = index === hoveredTabIndex;

          // Use session_name stored directly on tab (from plot_show event)
          const sessionName = tab.session_name || 'Agent';

          // Format tab label: "{session_name} Plot {plot_id}"
          const label = `${sessionName} Plot ${tab.plot_id}`;

          return (
            <div
              key={`${tab.plot_id}-${index}`}
              className={`
                flex items-center gap-2 px-3 py-2.5 cursor-pointer border-b-2
                whitespace-nowrap select-none transition-all min-w-0 flex-shrink-0
                ${isActive
                  ? 'text-gray-900 border-b-blue-500'
                  : 'text-gray-400 hover:text-gray-700 border-b-transparent'
                }
              `}
              onClick={() => onTabClick(index)}
              onMouseEnter={() => setHoveredTabIndex(index)}
              onMouseLeave={() => setHoveredTabIndex(null)}
            >
              {/* Tab label */}
              <span className="text-sm font-normal truncate">{label}</span>

              {/* Close button - always present but invisible when not hovered/active */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onTabClose(index);
                }}
                className={`
                  flex-shrink-0 text-gray-400 hover:text-gray-600 transition-opacity
                  ${(isHovered || isActive) ? 'opacity-100' : 'opacity-0'}
                `}
                title="Close tab"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-3.5 w-3.5"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
            </div>
          );
        })}
      </div>

      {/* Conditionally render buttons on this tab bar - RIGHTMOST */}
      {showButtons && (
        <TabBarButtons
          onNewTab={onNewTab}
          currentSessionId={currentSessionId}
          onSessionSwitch={onSessionSwitch}
        />
      )}
    </div>
  );
}
