import { useMemo } from 'react';

/**
 * MCTS Tree Visualization.
 *
 * Displays tree structure with clickable nodes.
 * Highlights best path and selected node.
 */
export function MCTSTreeView({
  nodes,        // [{ id, parent_id, score, status, name }]
  bestPath,     // [id1, id2, ...] - IDs of nodes in best path
  selectedNode, // Currently selected node ID
  onNodeClick,  // Called with node ID when clicked
}) {
  // Build tree structure from flat node list
  const tree = useMemo(() => {
    if (!nodes || nodes.length === 0) return null;

    const nodeMap = new Map();
    nodes.forEach(n => nodeMap.set(n.id, { ...n, children: [] }));

    let root = null;
    nodes.forEach(n => {
      const node = nodeMap.get(n.id);
      if (n.parent_id && nodeMap.has(n.parent_id)) {
        nodeMap.get(n.parent_id).children.push(node);
      } else if (!n.parent_id) {
        root = node;
      }
    });

    return root;
  }, [nodes]);

  const bestPathSet = useMemo(() => new Set(bestPath || []), [bestPath]);

  // Render a single node
  const renderNode = (node, depth = 0) => {
    const isSelected = node.id === selectedNode;
    const isBestPath = bestPathSet.has(node.id);
    const hasChildren = node.children && node.children.length > 0;

    // Status colors and labels
    const statusConfig = {
      // In-progress stages
      expanding: { color: 'bg-purple-500 animate-pulse', label: 'Coding...' },
      executing: { color: 'bg-blue-500 animate-pulse', label: 'Running...' },
      evaluating: { color: 'bg-cyan-500 animate-pulse', label: 'Evaluating...' },
      // Completed states
      running: { color: 'bg-blue-500 animate-pulse', label: null },
      completed: { color: 'bg-green-500', label: null },
      failed: { color: 'bg-red-500', label: null },
      pending: { color: 'bg-gray-300', label: null },
    };
    const statusInfo = statusConfig[node.status] || statusConfig.pending;
    const isInProgress = ['expanding', 'executing', 'evaluating'].includes(node.status);

    return (
      <div key={node.id} className="flex flex-col items-center">
        {/* Node */}
        <button
          onClick={() => onNodeClick?.(node.id)}
          className={`
            relative flex flex-col items-center justify-center
            w-16 h-16 rounded-xl transition-all
            ${isSelected
              ? 'ring-2 ring-blue-500 ring-offset-2 bg-blue-50'
              : node.is_buggy
                ? 'bg-red-50 hover:bg-red-100'
                : isInProgress
                  ? 'bg-purple-50 hover:bg-purple-100'
                  : 'hover:bg-gray-100 bg-white'
            }
            ${isBestPath ? 'shadow-lg shadow-yellow-200' : 'shadow'}
            border ${
              node.is_buggy ? 'border-red-300' :
              isBestPath ? 'border-yellow-400' :
              isInProgress ? 'border-purple-300' :
              'border-gray-200'
            }
          `}
        >
          {/* Status indicator */}
          <div className={`absolute top-1 right-1 w-2 h-2 rounded-full ${statusInfo.color}`} />

          {/* Score or in-progress label */}
          {isInProgress ? (
            <span className="text-xs font-medium text-purple-600 animate-pulse">
              {statusInfo.label}
            </span>
          ) : (
            <span className={`text-sm font-mono font-medium ${isBestPath ? 'text-yellow-700' : 'text-gray-700'}`}>
              {node.score !== null && node.score !== undefined
                ? node.score.toFixed(3)
                : '—'
              }
            </span>
          )}

          {/* Node name/ID (truncated) */}
          <span className="text-xs text-gray-400 truncate max-w-full px-1">
            {node.name || node.id.slice(0, 6)}
          </span>

          {/* Best path indicator */}
          {isBestPath && (
            <div className="absolute -top-1 -left-1">
              <svg className="w-4 h-4 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
              </svg>
            </div>
          )}
        </button>

        {/* Children */}
        {hasChildren && (
          <>
            {/* Connector line down */}
            <div className="w-px h-4 bg-gray-300" />

            {/* Horizontal connector and children */}
            <div className="flex items-start">
              {node.children.map((child, i) => (
                <div key={child.id} className="flex flex-col items-center">
                  {/* Horizontal line segment */}
                  {node.children.length > 1 && (
                    <div className={`h-px bg-gray-300 ${
                      i === 0 ? 'w-1/2 self-end' :
                      i === node.children.length - 1 ? 'w-1/2 self-start' :
                      'w-full'
                    }`} />
                  )}
                  {/* Vertical line down to child */}
                  <div className="w-px h-4 bg-gray-300" />
                  {/* Recursive child render */}
                  <div className="px-2">
                    {renderNode(child, depth + 1)}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    );
  };

  if (!tree) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400">
        <div className="text-center">
          <svg className="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
          </svg>
          <p>Waiting for MCTS tree...</p>
          <p className="text-sm mt-1">Nodes will appear as the search progresses</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-8">
      <div className="flex justify-center min-w-max">
        {renderNode(tree)}
      </div>
    </div>
  );
}
