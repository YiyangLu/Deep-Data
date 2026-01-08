import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Deep Plot summary component.
 *
 * Displays the final analysis summary with a toggle to show/hide
 * the full agent conversation.
 */
export function DeepPlotSummary({
  summary,
  evidencePlots,
  showConversation,
  onToggleConversation,
  children
}) {
  return (
    <div className="p-4">
      {/* Toggle conversation button - at the top */}
      <button
        onClick={onToggleConversation}
        className="flex items-center gap-2 mb-4 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
      >
        <svg
          className={`w-4 h-4 transition-transform ${showConversation ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <span>{showConversation ? 'Hide conversation' : 'Show conversation'}</span>
        <span className="text-gray-400 text-xs">({evidencePlots.length} evidence plots)</span>
      </button>

      {/* Collapsible conversation */}
      {showConversation && (
        <div className="mb-6 border-l-2 border-gray-200 pl-4">
          <div className="text-xs text-gray-500 mb-2 uppercase tracking-wide">Agent Conversation</div>
          {children}
        </div>
      )}

      {/* Summary content - using same styling as assistant messages */}
      <div className="markdown text-light-text">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {summary}
        </ReactMarkdown>
      </div>
    </div>
  );
}
