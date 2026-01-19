import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Single message component.
 *
 * Renders user messages, assistant messages, tool calls, and errors.
 */
export function Message({ message }) {
  // User message - right aligned with grey oval background
  if (message.role === 'user') {
    return (
      <div className="px-4 mb-4">
        <div className="text-right">
          <span className="inline-block bg-light-secondary px-4 py-2 rounded-3xl text-light-text whitespace-pre-wrap max-w-[80%] text-left" style={{ fontSize: '15px', lineHeight: '1.6' }}>
            {message.content}
          </span>
        </div>
      </div>
    );
  }

  // Assistant message - left aligned, plain text
  if (message.role === 'assistant') {
    return (
      <div className="px-4">
        <div className="markdown text-light-text">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        </div>
        {message.isStreaming && (
          <span className="typing-cursor inline-block w-2 h-5 bg-light-text ml-1" />
        )}
      </div>
    );
  }

  // Tool message - subtle indicator
  if (message.role === 'tool') {
    // Get first parameter value for display (similar to display.py approach)
    let firstParam = '';
    if (message.toolInput && typeof message.toolInput === 'object') {
      const values = Object.values(message.toolInput);
      if (values.length > 0) {
        const rawValue = values[0];
        // Convert to string representation
        let strValue = typeof rawValue === 'string' ? rawValue : JSON.stringify(rawValue);

        // Truncate if too long (max 60 chars)
        const maxLength = 60;
        if (strValue.length > maxLength) {
          strValue = strValue.substring(0, maxLength) + '...';
        }

        firstParam = strValue;
      }
    }

    return (
      <div className="px-4 mb-4">
        <div className="flex items-center gap-2 text-xs text-light-text-secondary">
          <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span className="font-mono truncate">
            {message.toolName}
            {firstParam && (
              <span className="text-light-text-secondary">({firstParam})</span>
            )}
          </span>
        </div>
      </div>
    );
  }

  // Error message - minimal styling
  if (message.role === 'error') {
    return (
      <div className="px-4 mb-4">
        <div className="flex items-start gap-2 text-red-600">
          <svg className="w-5 h-5 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  return null;
}
