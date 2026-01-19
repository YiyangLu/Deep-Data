import { useState, useRef, useEffect } from 'react';
import { TabBarButtons } from './TabBarButtons';

/**
 * Tab strip for managing multiple agent/session tabs.
 *
 * Displays tabs at the top of the chat panel, allowing users to
 * switch between multiple sessions and create new sessions.
 */
export function AgentTabs({
  tabs,
  activeTabIndex,
  onTabClick,
  onTabClose,
  onRenameTab,
  showButtons,
  onNewTab,
  currentSessionId,
  onSessionSwitch,
  onMleResume
}) {
  const [hoveredTabIndex, setHoveredTabIndex] = useState(null);
  const [editingTabIndex, setEditingTabIndex] = useState(null);
  const [editingValue, setEditingValue] = useState('');
  const tabStripRef = useRef(null);
  const inputRef = useRef(null);

  // Scroll active tab into view
  useEffect(() => {
    if (tabStripRef.current && activeTabIndex !== null) {
      const activeTab = tabStripRef.current.children[activeTabIndex];
      if (activeTab) {
        activeTab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
      }
    }
  }, [activeTabIndex]);

  // Focus input when editing starts
  useEffect(() => {
    if (editingTabIndex !== null && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingTabIndex]);

  // Handle double-click to start editing
  const handleDoubleClick = (index) => {
    const tab = tabs[index];
    if (tab) {
      setEditingTabIndex(index);
      setEditingValue(tab.session_name || 'Agent');
    }
  };

  // Handle Enter or blur to finish editing
  const handleFinishEditing = () => {
    if (editingTabIndex !== null && editingValue.trim()) {
      onRenameTab(editingTabIndex, editingValue.trim());
    }
    setEditingTabIndex(null);
    setEditingValue('');
  };

  // Handle Escape to cancel editing
  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleFinishEditing();
    } else if (e.key === 'Escape') {
      setEditingTabIndex(null);
      setEditingValue('');
    }
  };

  // Use session_name directly - names are unique at creation time
  const displayNames = tabs.map(tab => tab.session_name || 'Agent');

  return (
    <div className="flex items-center border-b border-gray-200 bg-white overflow-x-auto overflow-y-hidden">
      <div ref={tabStripRef} className="flex items-center min-w-0">
        {tabs.map((tab, index) => {
          const isActive = index === activeTabIndex;
          const isHovered = index === hoveredTabIndex;
          const isEditing = index === editingTabIndex;

          // Use session_name directly - names are unique at creation time
          const label = displayNames[index];

          return (
            <div
              key={tab.tab_id || `${tab.session_id}-${index}`}
              className={`
                flex items-center gap-2 px-3 py-2.5 border-b-2
                whitespace-nowrap select-none transition-all min-w-0 flex-shrink-0
                cursor-pointer
                ${isActive
                  ? 'text-gray-900 border-b-blue-500'
                  : 'text-gray-400 hover:text-gray-700 border-b-transparent'
                }
              `}
              onClick={() => !isEditing && onTabClick(index)}
              onDoubleClick={() => handleDoubleClick(index)}
              onMouseEnter={() => setHoveredTabIndex(index)}
              onMouseLeave={() => setHoveredTabIndex(null)}
            >
              {/* Tab label or input */}
              {isEditing ? (
                <input
                  ref={inputRef}
                  type="text"
                  value={editingValue}
                  onChange={(e) => setEditingValue(e.target.value)}
                  onBlur={handleFinishEditing}
                  onKeyDown={handleKeyDown}
                  className="text-sm font-normal px-1 py-0 border border-blue-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 min-w-[80px]"
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span className="text-sm font-normal truncate">{label}</span>
              )}

              {/* Close button - show for all tabs when editing is not active */}
              {!isEditing && (
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
              )}
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
          onMleResume={onMleResume}
        />
      )}
    </div>
  );
}
