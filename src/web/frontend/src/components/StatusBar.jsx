/**
 * Format token count for display (e.g., 1234 -> "1.2k")
 */
function formatTokens(count) {
  if (count >= 1000000) {
    return (count / 1000000).toFixed(1) + 'M';
  }
  if (count >= 1000) {
    return (count / 1000).toFixed(1) + 'k';
  }
  return count.toString();
}

/**
 * Status bar showing connection status and session info.
 */
export function StatusBar({ isConnected, sessionId, stats }) {
  // Extract token usage from stats
  const usage = stats?.usage || {};
  const inputTokens = usage.input_tokens;
  const outputTokens = usage.output_tokens;

  return (
    <div className="bg-light-bg border-b border-light-border px-4 py-3">
      <div className="max-w-4xl mx-auto flex items-center justify-between">
        {/* Left: Connection status */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-sm text-light-text-secondary">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          {sessionId && (
            <div className="text-xs text-light-text-secondary font-mono">
              {sessionId}
            </div>
          )}
        </div>

        {/* Right: Stats */}
        {stats && (
          <div className="flex items-center gap-4 text-xs text-light-text-secondary">
            {/* Token usage */}
            {(inputTokens !== undefined || outputTokens !== undefined) && (
              <div className="flex items-center gap-1" title="Input / Output tokens">
                <span className="text-blue-600">{inputTokens !== undefined ? formatTokens(inputTokens) : '-'}</span>
                <span>/</span>
                <span className="text-green-600">{outputTokens !== undefined ? formatTokens(outputTokens) : '-'}</span>
                <span className="text-light-text-secondary ml-0.5">tok</span>
              </div>
            )}
            {stats.num_turns !== undefined && (
              <div>Turns: {stats.num_turns}</div>
            )}
            {stats.total_cost_usd !== undefined && (
              <div>Cost: ${stats.total_cost_usd.toFixed(4)}</div>
            )}
            {stats.duration_ms !== undefined && (
              <div>Time: {(stats.duration_ms / 1000).toFixed(1)}s</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
