import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useAgentConnections } from './hooks/useAgentConnections';
import { usePlotTabs } from './hooks/usePlotTabs';
import { ChatWindow } from './components/ChatWindow';

/**
 * Main App component.
 *
 * Uses per-tab WebSocket connections for complete isolation.
 * Each agent tab has its own WebSocket, messages, stats, and processing state.
 */
function App() {
  // Plot-related state
  const [plotUrl, setPlotUrl] = useState(null);
  const [plotVisible, setPlotVisible] = useState(false);
  const [plotCommand, setPlotCommand] = useState(null);
  const [plotCacheClearTrigger, setPlotCacheClearTrigger] = useState(0);

  // Panel width and visibility state
  const [chatWidth, setChatWidth] = useState(100);
  const [chatVisible, setChatVisible] = useState(true);
  const [userHasAdjustedWidth, setUserHasAdjustedWidth] = useState(false);

  // Session type for new tabs (null = loading, 'new' shows selector, 'agent'/'deep_plot'/'mle'/'mle_running' for modes)
  const [activeSessionType, setActiveSessionType] = useState(null);
  const [isMLEAutoFilling, setIsMLEAutoFilling] = useState(false);

  // MLE run state
  const [mleStatus, setMleStatus] = useState(null);
  const [mleTree, setMleTree] = useState(null);
  const [mleSelectedNode, setMleSelectedNode] = useState(null);
  const [mleNodeLogs, setMleNodeLogs] = useState([]);
  const [mleRunId, setMleRunId] = useState(null);  // State (not ref) so polling effect re-runs

  // Track previous tab index to detect tab switches
  const prevTabIndexRef = useRef(-1);

  // Current working directory (user-editable for new sessions)
  // { cwd: string, shortened: string } or null if not loaded yet
  const [cwdInfo, setCwdInfo] = useState(null);

  // Load active MLE activity on mount (survives page reload)
  useEffect(() => {
    const loadActiveActivity = async () => {
      try {
        const response = await fetch('/api/activities/active/mle');
        if (response.ok) {
          const { activity } = await response.json();
          if (activity && (activity.status === 'running' || activity.status === 'paused')) {
            console.log('[App] Found active MLE activity:', activity.id);

            // Try to get status first - if 404, need to restore from journal
            const statusResponse = await fetch(`/api/mle/status/${activity.id}`);
            if (statusResponse.status === 404) {
              console.log('[App] MLE orchestrator not in memory, restoring from journal...');
              const restoreResponse = await fetch('/api/mle/restore', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ run_id: activity.id }),
              });
              if (!restoreResponse.ok) {
                console.error('[App] Failed to restore MLE:', await restoreResponse.text());
                return;
              }
              console.log('[App] MLE restored successfully');
            }

            setMleRunId(activity.id);
            setActiveSessionType('mle_running');
            // Polling effect will fetch full status once mleRunId is set
          }
        }
      } catch (err) {
        console.error('Failed to load active activity:', err);
      }
    };
    loadActiveActivity();
  }, []);  // Run once on mount

  // Refs for breaking circular dependencies
  const plotHandlersRef = useRef({
    handlePlotShow: null,
    handlePlotWorkspaceLoaded: null,
    filterToEvidencePlots: null
  });

  // Dummy saveWorkspace until real one is available
  const [saveWorkspaceReady, setSaveWorkspaceReady] = useState(false);
  const saveWorkspaceRef = useRef(null);

  // Stable saveWorkspace wrapper that uses ref
  const stableSaveWorkspace = useCallback((agentTabs, activeAgentIdx, plotTabs, activePlotIdx) => {
    if (saveWorkspaceRef.current) {
      saveWorkspaceRef.current(agentTabs, activeAgentIdx, plotTabs, activePlotIdx);
    }
  }, []);

  // Plot tabs hook (global across all sessions)
  // Initialize first so we can get the handlers
  const {
    tabs: plotTabs,
    activeTabIndex: activePlotTabIndex,
    setTabs: setPlotTabs,
    handlePlotShow,
    handleWorkspaceLoaded: handlePlotWorkspaceLoaded,
    handleTabClick: handlePlotTabClick,
    handleTabClose: handlePlotTabClose,
    handleClosePlot,
    filterToEvidencePlots,
    handlePlotsRenumbered,
    syncPlotsFromBackend
  } = usePlotTabs(
    null,  // currentSessionId - will be updated
    stableSaveWorkspace,
    userHasAdjustedWidth,
    setChatWidth,
    setPlotUrl,
    setPlotVisible
  );

  // Update refs when handlers change
  useEffect(() => {
    plotHandlersRef.current = {
      handlePlotShow,
      handlePlotWorkspaceLoaded,
      filterToEvidencePlots,
      handlePlotsRenumbered,
      syncPlotsFromBackend
    };
  }, [handlePlotShow, handlePlotWorkspaceLoaded, filterToEvidencePlots, handlePlotsRenumbered, syncPlotsFromBackend]);

  // Plot event handler (forwarded from useAgentConnections)
  const handlePlotEvent = useCallback((data) => {
    const { handlePlotShow } = plotHandlersRef.current;

    if (data.type === 'plot_show') {
      if (handlePlotShow) handlePlotShow(data);
    } else if (data.type === 'plot_command') {
      if (handlePlotShow) {
        handlePlotShow({
          plot_id: data.plot_id,
          session_id: data.session_id,
          session_name: data.session_name,
          url: `/plot/${data.session_id}/${data.plot_id}`,
          plot_type: 'plot'
        });
      }
      setPlotCommand({
        sessionId: data.session_id,
        plotId: data.plot_id,
        command: data.command,
        args: data.args,
        timestamp: Date.now()
      });
    } else if (data.type === 'plot_hide') {
      setPlotVisible(false);
    } else if (data.type === 'plots_renumbered') {
      // Update plot tabs with new IDs and remove non-evidence plots
      const { handlePlotsRenumbered } = plotHandlersRef.current;
      if (handlePlotsRenumbered) {
        handlePlotsRenumbered(data.id_mapping, data.final_plot_ids, data.session_id);
      }
      // Clear plot cache to force re-fetch with new IDs
      setPlotCacheClearTrigger(prev => prev + 1);
    }
  }, []);

  // Deep plot completion handler - sync plots from backend
  // This ensures all plots are correctly displayed even if WebSocket events were lost
  // (deepPlotReport is now stored per-tab in useAgentConnections)
  const handleDeepPlotComplete = useCallback((data) => {
    // Sync plots from backend to ensure tabs match reality
    // This is the self-healing mechanism for lost WebSocket events
    const sessionId = data.result?.session_id;
    if (sessionId) {
      const { syncPlotsFromBackend } = plotHandlersRef.current;
      if (syncPlotsFromBackend) {
        console.log('[App] deep_plot_complete - syncing plots from backend:', sessionId);
        syncPlotsFromBackend(sessionId);
      }
    }
  }, []);

  // Workspace loaded handler (for plot tabs and initial session type)
  const handleWorkspaceLoaded = useCallback((data) => {
    // Set initial session type based on loaded workspace
    const agentTabs = data.workspace?.agent_tabs || [];
    const activeIdx = data.workspace?.active_agent_tab;
    if (agentTabs.length > 0 && activeIdx !== null && activeIdx !== undefined && agentTabs[activeIdx]) {
      const activeTab = agentTabs[activeIdx];
      if (activeTab.type === 'mle') {
        setActiveSessionType('mle_running');
      } else {
        setActiveSessionType('agent');
      }
    } else {
      setActiveSessionType('new');
    }

    const { handlePlotWorkspaceLoaded } = plotHandlersRef.current;
    if (handlePlotWorkspaceLoaded) {
      handlePlotWorkspaceLoaded(data);
    }
  }, []);

  // Agent connections hook (one WebSocket per tab)
  const {
    tabs: agentTabs,
    activeTabIndex: activeAgentTabIndex,
    messages,
    stats,
    isProcessing,
    currentSessionId,
    deepPlotReport,
    createTab,
    closeTab,
    switchToTab,
    renameTab,
    sendQuery,
    sendDeepPlot,
    handleSessionSwitch,
    handleNewAgentTab,
    saveWorkspace,
    handleWorkspaceLoaded: initializeWorkspace
  } = useAgentConnections(handlePlotEvent, handleDeepPlotComplete, handleWorkspaceLoaded);

  // Fetch workspace via HTTP on mount (replaces control WebSocket)
  useEffect(() => {
    const loadWorkspace = async () => {
      try {
        const response = await fetch('/api/workspace');
        if (response.ok) {
          const data = await response.json();
          // Set cwd info
          if (data.cwd) {
            setCwdInfo(data.cwd);
          }
          // Initialize tabs and connections
          initializeWorkspace(data);
        }
      } catch (err) {
        console.error('[App] Failed to load workspace:', err);
        // Set session type to 'new' so UI is not stuck in loading state
        setActiveSessionType('new');
      }
    };
    loadWorkspace();
  }, [initializeWorkspace]);

  // Enrich plot tabs with session names from agent tabs
  // Agent tab names are unique at creation time, so simple lookup works
  const enrichedPlotTabs = useMemo(() => {
    const nameMap = Object.fromEntries(
      agentTabs.map(t => [t.session_id, t.session_name])
    );
    return plotTabs.map(tab => ({
      ...tab,
      session_name: nameMap[tab.session_id] || tab.session_name || 'Agent'
    }));
  }, [plotTabs, agentTabs]);

  // Update saveWorkspace ref when available
  useEffect(() => {
    if (saveWorkspace) {
      saveWorkspaceRef.current = saveWorkspace;
      setSaveWorkspaceReady(true);
    }
  }, [saveWorkspace]);

  // Create MLE tab if active activity exists but no MLE tab yet
  useEffect(() => {
    if (mleRunId && agentTabs.length > 0) {
      const hasMLETab = agentTabs.some(tab => tab.type === 'mle');
      if (!hasMLETab) {
        console.log('[App] Creating MLE tab for active activity:', mleRunId);
        createTab('MLE', 'mle', { mleRunId });
      }
    }
  }, [mleRunId, agentTabs, createTab]);

  // Handle send message
  const handleSendMessage = useCallback((content, mode = null) => {
    sendQuery(content, mode, cwdInfo?.cwd);
  }, [sendQuery, cwdInfo]);

  // Handle Deep Plot request
  const handleDeepPlot = useCallback(({ files, timeout, prompt }) => {
    sendDeepPlot({ files, timeout, prompt });
  }, [sendDeepPlot]);

  // Handle session type selection (from SessionTypeSelector)
  const handleSessionTypeSelect = useCallback((type) => {
    console.log(`[App] Session type selected: ${type}`);
    // If selecting MLE and a run is active, show dashboard instead of form
    if (type === 'mle' && mleRunId) {
      setActiveSessionType('mle_running');
    } else {
      setActiveSessionType(type);
    }
    // MLE has different UI (no plot panel), clear plot tabs for clean view
    if (type === 'mle' || type === 'mle_running') {
      setPlotTabs([]);
      setPlotVisible(false);
    }
  }, [setPlotTabs, mleRunId]);

  // Handle MLE start request
  const handleMLEStart = useCallback(async (config) => {
    console.log('MLE Start:', config);

    // Clear plot tabs for clean MLE view (MLE has different UI)
    setPlotTabs([]);
    setPlotVisible(false);

    // Reset MLE state and switch to dashboard immediately
    setMleStatus({
      workers: 0,
      total_workers: config.config?.workers || 2,  // Match MCTSConfig.DEFAULT_WORKERS
      best_score: null,
      steps: 0,
      max_steps: config.config?.max_steps || 100,
      elapsed: 0,
      cwd: config.workspace,  // MLE working directory
    });
    setMleTree(null);
    setMleSelectedNode(null);
    setMleNodeLogs([]);
    setActiveSessionType('mle_running');

    // Then call API
    try {
      const response = await fetch('/api/mle/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (response.ok) {
        const result = await response.json();
        setMleRunId(result.run_id);  // State update triggers polling effect
        // Create MLE tab with the run_id
        createTab('MLE', 'mle', { mleRunId: result.run_id });
      }
    } catch (err) {
      console.error('MLE start failed:', err);
    }
  }, [setPlotTabs, createTab]);

  // Helper to get current run_id (from state or active activity)
  const getActiveRunId = useCallback(async () => {
    if (mleRunId) return mleRunId;
    // Fallback: fetch from active activity API
    try {
      const response = await fetch('/api/activities/active/mle');
      if (response.ok) {
        const { activity } = await response.json();
        if (activity) {
          setMleRunId(activity.id);  // Update state for future use
          return activity.id;
        }
      }
    } catch (err) {
      console.error('Failed to get active activity:', err);
    }
    return null;
  }, [mleRunId]);

  // Handle MLE pause request
  const handleMLEPause = useCallback(async () => {
    const runId = await getActiveRunId();
    console.log('MLE Pause:', runId);
    if (!runId) {
      console.error('No run_id to pause');
      return;
    }
    try {
      const response = await fetch('/api/mle/pause', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId }),
      });
      if (response.ok) {
        // Update status to paused
        setMleStatus(prev => ({ ...prev, status: 'paused' }));
      } else {
        const error = await response.json();
        console.error('MLE pause failed:', error);
        // If run not found, clear the stale run_id
        if (response.status === 404) {
          setMleRunId(null);
        }
      }
    } catch (err) {
      console.error('MLE pause failed:', err);
    }
  }, [getActiveRunId]);

  // Handle MLE resume request
  const handleMLEResume = useCallback(async (additionalTime, additionalSteps) => {
    const runId = await getActiveRunId();
    console.log('MLE Resume:', runId, { additionalTime, additionalSteps });
    if (!runId) {
      console.error('No run_id to resume');
      return;
    }
    try {
      const response = await fetch('/api/mle/resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          additional_time: additionalTime,
          additional_steps: additionalSteps,
        }),
      });
      if (response.ok) {
        // Update status to running
        setMleStatus(prev => ({
          ...prev,
          status: 'running',
          max_steps: prev.steps + additionalSteps,
        }));
      } else {
        const error = await response.json();
        console.error('MLE resume failed:', error);
        // If run not found, clear the stale run_id
        if (response.status === 404) {
          setMleRunId(null);
        }
      }
    } catch (err) {
      console.error('MLE resume failed:', err);
    }
  }, [getActiveRunId]);

  // Handle MLE stop request (legacy, kept for compatibility)
  const handleMLEStop = useCallback(async () => {
    console.log('MLE Stop:', mleRunId);
    try {
      await fetch('/api/mle/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: mleRunId }),
      });
      // Switch back to MLE form
      setActiveSessionType('mle');
      setMleRunId(null);
    } catch (err) {
      console.error('MLE stop failed:', err);
    }
  }, [mleRunId]);

  // Handle MLE node selection (to show logs)
  const handleMLENodeSelect = useCallback(async (nodeId) => {
    console.log('MLE Node Select:', nodeId);
    setMleSelectedNode(nodeId);
    // Fetch logs for this node
    try {
      const response = await fetch(`/api/mle/node/${nodeId}/logs?run_id=${mleRunId}`);
      if (response.ok) {
        const result = await response.json();
        setMleNodeLogs(result.logs || []);
      }
    } catch (err) {
      console.error('Failed to fetch node logs:', err);
      setMleNodeLogs([]);
    }
  }, [mleRunId]);

  // Poll for node logs when a running node is selected
  useEffect(() => {
    if (!mleSelectedNode || !mleRunId || activeSessionType !== 'mle_running') {
      return;
    }

    // Check if selected node is in the running nodes list
    const runningNodes = mleTree?.in_progress || [];
    const isRunning = runningNodes.some(n => n.id === mleSelectedNode);

    if (!isRunning) {
      return;  // Don't poll for completed nodes
    }

    const pollLogs = async () => {
      try {
        const response = await fetch(`/api/mle/node/${mleSelectedNode}/logs?run_id=${mleRunId}`);
        if (response.ok) {
          const result = await response.json();
          setMleNodeLogs(result.logs || []);
        }
      } catch (err) {
        console.error('Failed to poll node logs:', err);
      }
    };

    // Poll every 1 second for running nodes
    const interval = setInterval(pollLogs, 1000);

    return () => clearInterval(interval);
  }, [mleSelectedNode, mleRunId, mleTree, activeSessionType]);

  // Poll for MLE status updates when running
  useEffect(() => {
    if (activeSessionType !== 'mle_running' || !mleRunId) {
      return;
    }

    const pollStatus = async () => {
      try {
        const response = await fetch(`/api/mle/status/${mleRunId}`);
        if (response.ok) {
          const data = await response.json();
          setMleStatus({
            status: data.status,  // Include status for UI state
            workers: data.workers,
            total_workers: data.total_workers,
            best_score: data.best_score,
            steps: data.steps,
            max_steps: data.max_steps,
            elapsed: data.elapsed,
            cwd: data.cwd,  // MLE working directory
          });
          setMleTree(data.tree);

          // Check if completed or stopped
          if (data.status === 'completed' || data.status === 'stopped' || data.status === 'error') {
            console.log('MLE run finished:', data.status);
          }
        } else if (response.status === 404) {
          // Run no longer exists (was reset or deleted)
          console.warn('MLE run not found, clearing state');
          setMleRunId(null);
          setMleStatus(prev => ({
            ...prev,
            status: 'error',
            error: 'Run was reset or no longer exists',
          }));
        }
      } catch (err) {
        console.error('Failed to poll MLE status:', err);
      }
    };

    // Poll immediately
    pollStatus();

    // Then poll every 2 seconds
    const interval = setInterval(pollStatus, 2000);

    return () => clearInterval(interval);
  }, [activeSessionType, mleRunId]);  // Re-run when mleRunId is set

  // Handle MLE discovery request (runs discovery agent)
  const handleMLEAutoFill = useCallback(async ({ partial_context = null, model = 'opus' } = {}) => {
    console.log('MLE Discovery: running discovery agent...', { partial_context, model });
    setIsMLEAutoFilling(true);
    try {
      const response = await fetch('/api/mle/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ partial_context, model }),
      });
      if (response.ok) {
        const result = await response.json();
        // Returns { context: {...}, config: {...} }
        return result;
      }
    } catch (err) {
      console.error('Discovery failed:', err);
    } finally {
      setIsMLEAutoFilling(false);
    }
    // Fallback: return null (no context discovered)
    return null;
  }, []);

  // Handle agent tab click - just switch tab, let useEffect sync session type
  const handleAgentTabClick = useCallback((index) => {
    const tab = agentTabs[index];
    if (tab) {
      switchToTab(tab.tab_id);
      // Restore mleRunId for MLE tabs
      if (tab.type === 'mle' && tab.mleRunId) {
        setMleRunId(tab.mleRunId);
      }
    }
  }, [agentTabs, switchToTab]);

  // Sync session type with active tab on tab switches (not initial load - that's handled by handleWorkspaceLoaded)
  useEffect(() => {
    if (activeAgentTabIndex >= 0) {
      const activeTab = agentTabs[activeAgentTabIndex];
      if (activeTab?.type === 'mle') {
        setActiveSessionType('mle_running');
        if (activeTab.mleRunId && !mleRunId) {
          setMleRunId(activeTab.mleRunId);
        }
      } else if (activeTab?.type === 'deep_plot' || activeTab?.type === 'agent') {
        setActiveSessionType('agent');
      }
    }
  }, [activeAgentTabIndex, agentTabs, mleRunId]);

  // Wrap handleNewAgentTab to also clear plot tabs and show selector
  const handleNewAgentTabWithReset = useCallback(() => {
    handleNewAgentTab();
    setPlotTabs([]);  // Clear plot tabs to give full width for session selector
    setPlotVisible(false);
    setActiveSessionType('new');  // Explicitly show selector (effect won't override for tabs without session_id)
  }, [handleNewAgentTab, setPlotTabs]);

  // Handle agent tab close
  const handleAgentTabClose = useCallback(async (index) => {
    const tab = agentTabs[index];
    if (tab) {
      // If closing an MLE tab, pause the active run
      if (tab.type === 'mle') {
        // Use tab.mleRunId or fallback to getActiveRunId
        const runId = tab.mleRunId || await getActiveRunId();
        if (runId) {
          try {
            await fetch('/api/mle/pause', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ run_id: runId }),
            });
            console.log('[App] Paused MLE run on tab close:', runId);
          } catch (err) {
            console.error('Failed to pause MLE on tab close:', err);
          }
        }
      }
      closeTab(tab.tab_id);
    }
  }, [agentTabs, closeTab, getActiveRunId]);

  // Handle MLE resume from history dropdown
  const handleMleResumeFromHistory = useCallback(async (activity) => {
    console.log('[App] Resume MLE from history:', activity);

    // Clear plot tabs for MLE view
    setPlotTabs([]);
    setPlotVisible(false);
    setActiveSessionType('mle_running');

    // First, try to restore the orchestrator state from journal
    try {
      const response = await fetch('/api/mle/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: activity.id }),
      });

      if (response.ok) {
        const result = await response.json();
        console.log('[App] MLE restored:', result);

        // Initialize status with restored state
        setMleStatus({
          status: activity.status,
          workers: 0,
          total_workers: activity.config?.workers || 2,  // Match MCTSConfig.DEFAULT_WORKERS
          best_score: result.best_score,
          steps: result.current_step || 0,
          max_steps: activity.config?.max_steps || 100,
          elapsed: result.time_elapsed || 0,
          cwd: activity.cwd || activity.config?.workspace,  // MLE working directory
        });
      } else {
        console.warn('[App] Failed to restore MLE, will show empty state');
      }
    } catch (err) {
      console.error('[App] Failed to restore MLE:', err);
    }

    // Set the run ID - this triggers the polling effect
    setMleRunId(activity.id);

    // Create MLE tab if not exists
    const hasMLETab = agentTabs.some(tab => tab.type === 'mle');
    if (!hasMLETab) {
      createTab('MLE', 'mle', { mleRunId: activity.id });
    } else {
      // If MLE tab exists, update its run ID and switch to it
      const mleTab = agentTabs.find(tab => tab.type === 'mle');
      if (mleTab) {
        switchToTab(mleTab.tab_id);
      }
    }
  }, [agentTabs, createTab, switchToTab, setPlotTabs]);

  // Handle agent tab rename
  const handleRenameAgentTab = useCallback((index, newName) => {
    const tab = agentTabs[index];
    if (tab) {
      renameTab(tab.tab_id, newName);
    }
  }, [agentTabs, renameTab]);

  // Panel handlers
  const handleResize = useCallback((newChatWidth) => {
    setChatWidth(newChatWidth);
    setUserHasAdjustedWidth(true);
  }, []);

  const handleHideChat = useCallback(() => setChatVisible(false), []);
  const handleHidePlot = useCallback(() => setPlotVisible(false), []);
  const handleShowChat = useCallback(() => setChatVisible(true), []);

  const handleShowPlot = useCallback(() => {
    setPlotVisible(true);
    if (!userHasAdjustedWidth) {
      setChatWidth(25);
    }
  }, [userHasAdjustedWidth]);

  const handleRecoverPlot = useCallback((plotData) => {
    handlePlotShow({
      plot_id: plotData.plot_id,
      session_id: plotData.session_id,
      session_name: plotData.session_name,
      url: plotData.plot_url,
      plot_type: 'plot'
    });
  }, [handlePlotShow]);

  return (
    <ChatWindow
      sessionId={currentSessionId}
      messages={messages}
      stats={stats}
      onSendMessage={handleSendMessage}
      onDeepPlot={handleDeepPlot}
      onMLEStart={handleMLEStart}
      onMLEAutoFill={handleMLEAutoFill}
      isMLEAutoFilling={isMLEAutoFilling}
      onMLEStop={handleMLEStop}
      onMLEPause={handleMLEPause}
      onMLEResume={handleMLEResume}
      mleStatus={mleStatus}
      mleTree={mleTree}
      mleSelectedNode={mleSelectedNode}
      mleNodeLogs={mleNodeLogs}
      onMLENodeSelect={handleMLENodeSelect}
      isProcessing={isProcessing}
      plotUrl={plotUrl}
      plotVisible={plotVisible}
      onClosePlot={handleClosePlot}
      chatWidth={chatWidth}
      chatVisible={chatVisible}
      onResize={handleResize}
      onHideChat={handleHideChat}
      onHidePlot={handleHidePlot}
      onShowChat={handleShowChat}
      onShowPlot={handleShowPlot}
      onSessionSwitch={handleSessionSwitch}
      tabs={enrichedPlotTabs}
      activeTabIndex={activePlotTabIndex}
      onTabClick={handlePlotTabClick}
      onTabClose={handlePlotTabClose}
      agentTabs={agentTabs}  // For AgentTabs component
      activeAgentTabIndex={activeAgentTabIndex}
      activeSessionType={activeSessionType}
      onSessionTypeSelect={handleSessionTypeSelect}
      onAgentTabClick={handleAgentTabClick}
      onAgentTabClose={handleAgentTabClose}
      onNewAgentTab={handleNewAgentTabWithReset}
      onRenameAgentTab={handleRenameAgentTab}
      onMleResumeFromHistory={handleMleResumeFromHistory}
      onRecoverPlot={handleRecoverPlot}
      plotCommand={plotCommand}
      deepPlotReport={deepPlotReport}
      isNewSession={activeAgentTabIndex < 0 || (messages.length === 0 && !isProcessing && !agentTabs[activeAgentTabIndex]?.session_id)}
      cwdInfo={cwdInfo}
      onCwdChange={setCwdInfo}
      plotCacheClearTrigger={plotCacheClearTrigger}
    />
  );
}

export default App;
