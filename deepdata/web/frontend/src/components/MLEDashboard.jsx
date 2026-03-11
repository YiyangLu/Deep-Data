import { useState } from 'react';
import { MCTSTreeView } from './MCTSTreeView';
import { MLEStatusBar } from './MLEStatusBar';
import { NodeLogPanel } from './NodeLogPanel';

/**
 * MLE Dashboard - main view after starting MLE run.
 *
 * Shows MCTS tree as main visualization with status bar at bottom.
 * Click tree node to show logs in right panel.
 */
export function MLEDashboard({
  status,        // { status, workers, best_score, steps, max_steps, elapsed }
  tree,          // { nodes: [...], best_path: [...] }
  selectedNode,  // Currently selected node ID
  nodeLogs,      // Logs for selected node
  onNodeSelect,  // Called when user clicks a node
  onPause,       // Called when user clicks Pause
  onResume,      // Called when user clicks Resume (additionalTime, additionalSteps)
}) {
  const [logPanelVisible, setLogPanelVisible] = useState(false);

  const handleNodeClick = (nodeId) => {
    onNodeSelect?.(nodeId);
    setLogPanelVisible(true);
  };

  const handleCloseLogPanel = () => {
    setLogPanelVisible(false);
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Main content area */}
      <div className="flex-1 flex min-h-0">
        {/* MCTS Tree - main view */}
        <div className={`flex-1 min-w-0 overflow-auto ${logPanelVisible ? '' : 'w-full'}`}>
          <MCTSTreeView
            nodes={tree?.nodes || []}
            bestPath={tree?.best_path || []}
            selectedNode={selectedNode}
            onNodeClick={handleNodeClick}
          />
        </div>

        {/* Log Panel - right side, hidden by default */}
        {logPanelVisible && (
          <div className="w-96 border-l border-gray-200 flex-shrink-0">
            <NodeLogPanel
              nodeId={selectedNode}
              logs={nodeLogs}
              onClose={handleCloseLogPanel}
            />
          </div>
        )}
      </div>

      {/* Status Bar - bottom */}
      <MLEStatusBar
        status={status?.status || 'starting'}
        workers={status?.workers || 0}
        totalWorkers={status?.total_workers || 0}
        bestScore={status?.best_score}
        steps={status?.steps || 0}
        maxSteps={status?.max_steps || 100}
        elapsed={status?.elapsed || 0}
        error={status?.error}
        cwd={status?.cwd}
        onPause={onPause}
        onResume={onResume}
      />
    </div>
  );
}
