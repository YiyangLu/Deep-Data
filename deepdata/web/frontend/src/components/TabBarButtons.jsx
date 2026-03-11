import { SessionHistoryDropdown } from './SessionHistoryDropdown';

/**
 * Shared button component for tab bars (new session and history buttons).
 *
 * Used by both AgentTabs and PlotTabs to provide consistent button UI.
 */
export function TabBarButtons({ onNewTab, currentSessionId, onSessionSwitch, onMleResume }) {
  return (
    <>
      {/* "+" button for new tab */}
      <button
        className="flex items-center justify-center py-2.5 px-1.5 text-gray-600 hover:bg-gray-100 rounded transition-colors border-b-2 border-b-transparent ml-auto mr-1"
        onClick={onNewTab}
        title="New session"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-5 w-5"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {/* Session History Button */}
      <div className="mr-3 flex items-center">
        <SessionHistoryDropdown
          currentSessionId={currentSessionId}
          onSessionSwitch={onSessionSwitch}
          onMleResume={onMleResume}
        />
      </div>
    </>
  );
}
