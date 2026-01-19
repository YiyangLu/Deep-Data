import { useEffect, useRef, useState } from 'react';
import { Message } from './Message';
import { DeepPlotSummary } from './DeepPlotSummary';

/**
 * Scrollable message list component.
 *
 * Auto-scrolls to bottom on new messages.
 * Shows loading state when isLoading is true and messages are empty.
 * When deepPlotReport is provided, shows summary with collapsible conversation.
 */
export function MessageList({ messages, isLoading = false, deepPlotReport = null }) {
  const messagesEndRef = useRef(null);
  const containerRef = useRef(null);
  const [showConversation, setShowConversation] = useState(false);

  // Auto-scroll to bottom when NEW messages arrive (not history)
  useEffect(() => {
    // Don't auto-scroll if the last message is from history
    const lastMessage = messages[messages.length - 1];
    const isHistoryLoad = lastMessage?.isHistory === true;

    if (messagesEndRef.current && !isHistoryLoad) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Reset conversation visibility when deepPlotReport changes
  useEffect(() => {
    if (deepPlotReport) {
      setShowConversation(false);
    }
  }, [deepPlotReport]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto scrollbar-thin"
    >
      {messages.length === 0 ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-center px-4">
            {isLoading ? (
              <div className="text-gray-400">Loading conversation...</div>
            ) : (
              <h2 className="text-3xl font-medium text-light-text mb-8">
                What can I help with?
              </h2>
            )}
          </div>
        </div>
      ) : deepPlotReport ? (
        /* Deep Plot completed - show summary with collapsible conversation */
        <DeepPlotSummary
          summary={deepPlotReport.summary}
          evidencePlots={deepPlotReport.evidence_plots}
          showConversation={showConversation}
          onToggleConversation={() => setShowConversation(!showConversation)}
        >
          {/* Conversation is rendered as children when expanded */}
          {showConversation && (
            <>
              {messages.map((message) => (
                <Message key={message.id} message={message} />
              ))}
            </>
          )}
        </DeepPlotSummary>
      ) : (
        /* Normal conversation view */
        <>
          {messages.map((message) => (
            <Message key={message.id} message={message} />
          ))}
          <div ref={messagesEndRef} />
        </>
      )}
    </div>
  );
}
