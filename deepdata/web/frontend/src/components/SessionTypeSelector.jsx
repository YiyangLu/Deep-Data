/**
 * Session type selector shown when creating a new tab.
 *
 * Displays cards for each session type: Agent, Deep Plot, MLE.
 * User clicks a card to transform the tab into that type.
 */

export function SessionTypeSelector({ onSelect }) {
  const sessionTypes = [
    {
      id: 'agent',
      name: 'Agent',
      icon: (
        <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      ),
      description: 'Coding agent for verified interactive visualization',
      color: 'blue',
    },
    {
      id: 'deep_plot',
      name: 'Deep Plot',
      icon: (
        <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
      description: 'Autonomous data analysis agent with iterative exploration and explanation',
      color: 'purple',
    },
    {
      id: 'mle',
      name: 'MLE',
      icon: (
        <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      ),
      description: 'MCTS-based ML solution search with parallel workers',
      color: 'green',
    },
  ];

  const colorClasses = {
    blue: {
      bg: 'bg-blue-50 hover:bg-blue-100',
      border: 'border-blue-200 hover:border-blue-300',
      icon: 'text-blue-600',
      text: 'text-blue-900',
    },
    purple: {
      bg: 'bg-purple-50 hover:bg-purple-100',
      border: 'border-purple-200 hover:border-purple-300',
      icon: 'text-purple-600',
      text: 'text-purple-900',
    },
    green: {
      bg: 'bg-green-50 hover:bg-green-100',
      border: 'border-green-200 hover:border-green-300',
      icon: 'text-green-600',
      text: 'text-green-900',
    },
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <h2 className="text-xl font-medium text-gray-900 mb-2">New Session</h2>
      <p className="text-gray-500 mb-8">Choose a session type to get started</p>

      <div className="flex gap-4">
        {sessionTypes.map((type) => {
          const colors = colorClasses[type.color];
          return (
            <button
              key={type.id}
              onClick={() => onSelect(type.id)}
              className={`flex flex-col items-center p-6 rounded-xl border-2 transition-all ${colors.bg} ${colors.border} w-48`}
            >
              <div className={`mb-3 ${colors.icon}`}>
                {type.icon}
              </div>
              <h3 className={`font-medium mb-2 ${colors.text}`}>
                {type.name}
              </h3>
              <p className="text-sm text-gray-600 text-center">
                {type.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
