import { useState, useCallback, useRef, useEffect } from 'react';

/**
 * Generate a unique tab ID.
 */
function generateTabId() {
  return `tab_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Convert conversation history blocks to UI message format.
 */
function convertBlocksToMessages(blocks) {
  if (!blocks || !Array.isArray(blocks)) return [];

  return blocks.map((block) => {
    if (block.type === 'text') {
      return {
        id: `history_${block.turn_number}_${block.block_index}`,
        role: block.role || 'assistant',
        content: block.text || block.text_content || '',
        timestamp: new Date(block.timestamp || Date.now()),
        isHistory: true
      };
    } else if (block.type === 'tool_use') {
      return {
        id: `history_tool_${block.turn_number}_${block.block_index}`,
        role: 'tool',
        toolName: block.name,
        toolInput: block.input,
        timestamp: new Date(block.timestamp || Date.now()),
        isHistory: true
      };
    }
    return null;
  }).filter(Boolean);
}

/**
 * Migrate workspace from old formats.
 */
function migrateWorkspace(tabs) {
  if (!tabs || !Array.isArray(tabs)) return [];

  return tabs
    .filter(tab => tab.session_id && !tab.session_id.startsWith('web_agent_'))
    .map(tab => ({
      ...tab,
      tab_id: tab.tab_id || generateTabId(),
      status: tab.status || 'active'
    }));
}

/**
 * Custom hook for managing agent connections.
 *
 * Each agent tab gets its own WebSocket connection, providing complete isolation.
 * This eliminates race conditions when switching tabs during agent processing.
 *
 * @param {Function} onPlotEvent - Callback for plot events (plot_show, plot_command)
 * @param {Function} onDeepPlotComplete - Callback for deep plot completion
 * @param {Function} onWorkspaceLoaded - Callback when workspace is first loaded
 */
export function useAgentConnections(onPlotEvent, onDeepPlotComplete, onWorkspaceLoaded) {
  // Tab metadata
  const [tabs, setTabs] = useState([]);
  const [activeTabId, setActiveTabId] = useState(null);

  // Per-tab connection state
  const [connections, setConnections] = useState({});

  // WebSocket refs (not state - avoid re-renders)
  const wsRefs = useRef({});
  const reconnectTimeoutsRef = useRef({});
  const pendingMessagesRef = useRef({});  // Messages queued while connecting

  // Track if initial workspace has loaded
  const workspaceLoadedRef = useRef(false);

  // Workspace save timeout for debouncing
  const saveTimeoutRef = useRef(null);

  // Control WebSocket for initial workspace loading
  const controlWsRef = useRef(null);
  const controlConnectedRef = useRef(false);

  // ========== Helper Functions ==========

  const updateConnection = useCallback((tabId, updates) => {
    setConnections(prev => ({
      ...prev,
      [tabId]: { ...prev[tabId], ...updates }
    }));
  }, []);

  const updateTab = useCallback((tabId, updates) => {
    setTabs(prev => prev.map(t =>
      t.tab_id === tabId ? { ...t, ...updates } : t
    ));
  }, []);

  /**
   * Get any available connected WebSocket for sending commands.
   * Prefers tab WebSockets, falls back to control WebSocket.
   */
  const getAnyConnectedWs = useCallback(() => {
    // First try tab WebSockets
    for (const tabId of Object.keys(wsRefs.current)) {
      const ws = wsRefs.current[tabId];
      if (ws && ws.readyState === WebSocket.OPEN) {
        return ws;
      }
    }
    // Fall back to control WebSocket
    if (controlWsRef.current && controlWsRef.current.readyState === WebSocket.OPEN) {
      return controlWsRef.current;
    }
    return null;
  }, []);

  /**
   * Save workspace state (debounced).
   * Uses any available WebSocket connection.
   */
  const saveWorkspaceInternal = useCallback((currentTabs, activeIdx, plotTabs = null, activePlotIdx = null) => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }

    saveTimeoutRef.current = setTimeout(() => {
      const ws = getAnyConnectedWs();
      if (!ws) {
        console.log('[useAgentConnections] No connected WebSocket for workspace save');
        return;
      }

      const workspace = { version: 3 };

      // Include agent_tabs - map to simpler format for storage
      if (currentTabs) {
        workspace.agent_tabs = currentTabs.map(tab => ({
          tab_id: tab.tab_id,
          session_id: tab.session_id,
          session_name: tab.session_name,
          type: tab.type || 'agent',
          mleRunId: tab.mleRunId,  // Preserve MLE run ID for tab restoration
          created_at: tab.created_at || new Date().toISOString()
        }));
        workspace.active_agent_tab = activeIdx;
      }

      // Include plot_tabs if provided
      if (plotTabs !== null) {
        workspace.plot_tabs = plotTabs.map(tab => ({
          plot_id: tab.plot_id,
          session_id: tab.session_id,
          session_name: tab.session_name,
          plot_type: tab.plot_type,
          plot_url: tab.plot_url,
          created_at: tab.created_at || new Date().toISOString()
        }));
        workspace.active_plot_tab = activePlotIdx;
      }

      ws.send(JSON.stringify({
        type: 'save_workspace',
        workspace
      }));
    }, 500);
  }, [getAnyConnectedWs]);

  // ========== Message Handling ==========

  const addUserMessage = useCallback((tabId, content) => {
    const message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date()
    };

    setConnections(prev => ({
      ...prev,
      [tabId]: {
        ...prev[tabId],
        messages: [...(prev[tabId]?.messages || []), message]
      }
    }));
  }, []);

  const startStreaming = useCallback((tabId, messageId) => {
    setConnections(prev => ({
      ...prev,
      [tabId]: {
        ...prev[tabId],
        currentMessage: {
          id: messageId,
          role: 'assistant',
          content: '',
          isStreaming: true,
          timestamp: new Date()
        },
        isProcessing: true
      }
    }));
  }, []);

  const appendChunk = useCallback((tabId, messageId, chunk) => {
    setConnections(prev => {
      const conn = prev[tabId];
      if (!conn?.currentMessage || conn.currentMessage.id !== messageId) {
        return prev;
      }
      return {
        ...prev,
        [tabId]: {
          ...conn,
          currentMessage: {
            ...conn.currentMessage,
            content: conn.currentMessage.content + chunk
          }
        }
      };
    });
  }, []);

  const finishStreaming = useCallback((tabId, messageId) => {
    setConnections(prev => {
      const conn = prev[tabId];
      if (!conn?.currentMessage || conn.currentMessage.id !== messageId) {
        return prev;
      }
      return {
        ...prev,
        [tabId]: {
          ...conn,
          messages: [...conn.messages, { ...conn.currentMessage, isStreaming: false }],
          currentMessage: null
        }
      };
    });
  }, []);

  const addToolMessage = useCallback((tabId, data) => {
    const message = {
      id: `${data.message_id}_tool_${Date.now()}`,
      role: 'tool',
      toolName: data.name || data.tool_name,
      toolInput: data.input || data.tool_input,
      timestamp: new Date()
    };

    setConnections(prev => ({
      ...prev,
      [tabId]: {
        ...prev[tabId],
        messages: [...(prev[tabId]?.messages || []), message]
      }
    }));
  }, []);

  const addErrorMessage = useCallback((tabId, error) => {
    const message = {
      id: Date.now().toString(),
      role: 'error',
      content: error,
      timestamp: new Date()
    };

    setConnections(prev => ({
      ...prev,
      [tabId]: {
        ...prev[tabId],
        messages: [...(prev[tabId]?.messages || []), message]
      }
    }));
  }, []);

  // ========== WebSocket Message Handler ==========

  const handleTabMessage = useCallback((tabId, data) => {
    switch (data.type) {
      case 'connected':
        // WebSocket connected confirmation
        break;

      case 'session_info':
        updateConnection(tabId, { sessionId: data.session_id });
        updateTab(tabId, {
          session_id: data.session_id,
          session_name: data.session_name || 'Agent',
          status: 'active'
        });
        break;

      case 'conversation_history':
        const historyMsgs = convertBlocksToMessages(data.blocks);
        updateConnection(tabId, {
          messages: historyMsgs,
          isProcessing: false
        });
        break;

      case 'session_stats':
        if (data.stats) {
          updateConnection(tabId, { stats: data.stats });
        }
        break;

      case 'text_start':
        startStreaming(tabId, data.message_id);
        break;

      case 'text_chunk':
        appendChunk(tabId, data.message_id, data.content);
        break;

      case 'text_end':
        finishStreaming(tabId, data.message_id);
        break;

      case 'tool_use':
      case 'tool_start':
        addToolMessage(tabId, data);
        break;

      case 'complete':
        updateConnection(tabId, {
          isProcessing: false,
          stats: data.stats || {}
        });
        break;

      case 'deep_plot_complete':
        updateConnection(tabId, { isProcessing: false });
        if (data.result) {
          const report = data.result.summary ? {
            summary: data.result.summary,
            evidence_plots: data.result.evidence_plots || []
          } : null;
          updateConnection(tabId, {
            stats: {
              total_cost_usd: data.result.total_cost_usd,
              duration_ms: data.result.duration_ms,
              num_turns: data.result.iteration_count
            },
            deepPlotReport: report
          });
        }
        onDeepPlotComplete?.(data);
        break;

      case 'error':
        addErrorMessage(tabId, data.error);
        updateConnection(tabId, { isProcessing: false });
        break;

      case 'plot_show':
        onPlotEvent?.({
          ...data,
          type: 'plot_show'
        });
        break;

      case 'plot_command':
        onPlotEvent?.({
          ...data,
          type: 'plot_command'
        });
        break;

      case 'plot_hide':
        onPlotEvent?.({ type: 'plot_hide' });
        break;

      case 'workspace_loaded':
        // This will be handled by handleWorkspaceLoaded
        // The first WebSocket to receive this triggers workspace loading
        break;

      case 'rename_session_result':
        if (data.success) {
          updateTab(tabId, { session_name: data.session_name });
        }
        break;

      default:
        // Ignore unknown message types
        break;
    }
  }, [
    updateConnection,
    updateTab,
    startStreaming,
    appendChunk,
    finishStreaming,
    addToolMessage,
    addErrorMessage,
    onPlotEvent,
    onDeepPlotComplete
  ]);

  // ========== WebSocket Management ==========

  const connectTab = useCallback((tabId, resumeSessionId = null) => {
    // Don't reconnect if already connected
    if (wsRefs.current[tabId]?.readyState === WebSocket.OPEN) {
      return;
    }

    // Clear any existing reconnect timeout
    if (reconnectTimeoutsRef.current[tabId]) {
      clearTimeout(reconnectTimeoutsRef.current[tabId]);
      delete reconnectTimeoutsRef.current[tabId];
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    console.log(`[useAgentConnections] Connecting tab ${tabId}`, resumeSessionId ? `(resume: ${resumeSessionId})` : '(new)');

    updateConnection(tabId, { state: 'connecting' });

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log(`[useAgentConnections] Tab ${tabId} connected`);
      updateConnection(tabId, { state: 'connected' });

      // If resuming, send activate_session
      if (resumeSessionId) {
        ws.send(JSON.stringify({
          type: 'activate_session',
          session_id: resumeSessionId
        }));
      }

      // Send any pending messages
      const pending = pendingMessagesRef.current[tabId];
      if (pending) {
        console.log(`[useAgentConnections] Sending pending message for tab ${tabId}`);
        ws.send(JSON.stringify(pending));
        delete pendingMessagesRef.current[tabId];
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleTabMessage(tabId, data);
      } catch (err) {
        console.error(`[useAgentConnections] Error parsing message for tab ${tabId}:`, err);
      }
    };

    ws.onerror = (event) => {
      console.error(`[useAgentConnections] WebSocket error for tab ${tabId}:`, event);
      updateConnection(tabId, { state: 'error' });
    };

    ws.onclose = () => {
      console.log(`[useAgentConnections] Tab ${tabId} disconnected`);
      updateConnection(tabId, { state: 'disconnected' });

      // Auto-reconnect after 3s if tab still exists
      reconnectTimeoutsRef.current[tabId] = setTimeout(() => {
        // Check if tab still exists
        setTabs(currentTabs => {
          const tabExists = currentTabs.some(t => t.tab_id === tabId);
          if (tabExists) {
            // Get current session_id for reconnection
            setConnections(currentConns => {
              const sessionId = currentConns[tabId]?.sessionId;
              if (sessionId) {
                connectTab(tabId, sessionId);
              }
              return currentConns;
            });
          }
          return currentTabs;
        });
      }, 3000);
    };

    wsRefs.current[tabId] = ws;
  }, [handleTabMessage, updateConnection]);

  const disconnectTab = useCallback((tabId) => {
    console.log(`[useAgentConnections] Disconnecting tab ${tabId}`);

    // Clear reconnect timeout
    if (reconnectTimeoutsRef.current[tabId]) {
      clearTimeout(reconnectTimeoutsRef.current[tabId]);
      delete reconnectTimeoutsRef.current[tabId];
    }

    // Clear pending messages
    delete pendingMessagesRef.current[tabId];

    // Close WebSocket
    const ws = wsRefs.current[tabId];
    if (ws) {
      ws.onclose = null;  // Prevent reconnection attempt
      ws.close();
      delete wsRefs.current[tabId];
    }
  }, []);

  // ========== Tab Management ==========

  const createTab = useCallback((sessionName = 'Agent', type = 'agent', metadata = {}) => {
    const tabId = generateTabId();
    console.log(`[useAgentConnections] Creating tab ${tabId} (${sessionName}, type=${type})`);

    const newTab = {
      tab_id: tabId,
      session_id: null,
      session_name: sessionName,
      type: type,  // 'agent' | 'deep_plot' | 'mle'
      status: type === 'mle' ? 'active' : 'pending',  // MLE tabs are immediately active (no websocket needed)
      created_at: new Date().toISOString(),
      ...metadata  // Additional data like mleRunId for MLE tabs
    };

    setTabs(prev => [...prev, newTab]);

    // MLE tabs don't need websocket connections
    if (type !== 'mle') {
      setConnections(prev => ({
        ...prev,
        [tabId]: {
          state: 'idle',
          sessionId: null,
          messages: [],
          currentMessage: null,
          stats: {},
          isProcessing: false,
          deepPlotReport: null
        }
      }));
    }
    setActiveTabId(tabId);

    return tabId;
  }, []);

  const closeTab = useCallback((tabId) => {
    console.log(`[useAgentConnections] Closing tab ${tabId}`);

    disconnectTab(tabId);

    setTabs(prev => {
      const newTabs = prev.filter(t => t.tab_id !== tabId);

      // Update active tab if needed
      setActiveTabId(currentActiveId => {
        if (currentActiveId !== tabId) {
          return currentActiveId;
        }

        // Find new active tab
        const closedIndex = prev.findIndex(t => t.tab_id === tabId);
        if (newTabs.length === 0) {
          return null;
        } else if (closedIndex > 0) {
          return newTabs[closedIndex - 1].tab_id;
        } else {
          return newTabs[0].tab_id;
        }
      });

      // Save workspace
      const activeIdx = newTabs.findIndex(t => t.tab_id === activeTabId);
      saveWorkspaceInternal(newTabs, activeIdx >= 0 ? activeIdx : null, null, null);

      return newTabs;
    });

    setConnections(prev => {
      const newConns = { ...prev };
      delete newConns[tabId];
      return newConns;
    });
  }, [disconnectTab, activeTabId, saveWorkspaceInternal]);

  const switchToTab = useCallback((tabId) => {
    console.log(`[useAgentConnections] Switching to tab ${tabId}`);
    setActiveTabId(tabId);

    // Save workspace with new active tab
    setTabs(currentTabs => {
      const activeIdx = currentTabs.findIndex(t => t.tab_id === tabId);
      saveWorkspaceInternal(currentTabs, activeIdx, null, null);
      return currentTabs;
    });
  }, [saveWorkspaceInternal]);

  const renameTab = useCallback((tabId, newName) => {
    const ws = wsRefs.current[tabId];
    const conn = connections[tabId];

    if (!ws || ws.readyState !== WebSocket.OPEN || !conn?.sessionId) {
      return;
    }

    ws.send(JSON.stringify({
      type: 'rename_session',
      session_id: conn.sessionId,
      new_name: newName
    }));
  }, [connections]);

  // ========== Query ==========

  const sendQuery = useCallback((content, mode = null) => {
    const sessionName = mode === 'deep_plot' ? 'Deep Plot' : 'Agent';
    let tabId = activeTabId;

    // Create tab if none active
    if (!tabId) {
      tabId = createTab(sessionName);
    }

    // Add user message
    addUserMessage(tabId, content);
    updateConnection(tabId, { isProcessing: true });

    const message = {
      type: 'message',
      content,
      session_name: sessionName,
      new_session: !connections[tabId]?.sessionId
    };

    const ws = wsRefs.current[tabId];

    // Connect if not connected
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.log(`[useAgentConnections] Tab ${tabId} not connected, queuing message`);
      pendingMessagesRef.current[tabId] = message;
      connectTab(tabId);
    } else {
      ws.send(JSON.stringify(message));
    }
  }, [activeTabId, connections, createTab, addUserMessage, updateConnection, connectTab]);

  const sendDeepPlot = useCallback(({ files, timeout, prompt }) => {
    const tabId = createTab('Deep Plot', 'deep_plot');

    // Add user message
    const fileList = files.join(', ');
    addUserMessage(tabId, `[Deep Plot] Analyzing ${fileList} for ${timeout}s: ${prompt}`);
    updateConnection(tabId, { isProcessing: true });

    const message = {
      type: 'deep_plot',
      files,
      timeout,
      prompt
    };

    // Queue message and connect
    pendingMessagesRef.current[tabId] = message;
    connectTab(tabId);
  }, [createTab, addUserMessage, updateConnection, connectTab]);

  // ========== Session Switch (from history) ==========

  const handleSessionSwitch = useCallback((sessionId, sessionName = 'Agent') => {
    console.log(`[useAgentConnections] Switching to session ${sessionId}`);

    const tabId = generateTabId();
    const newTab = {
      tab_id: tabId,
      session_id: sessionId,
      session_name: sessionName,
      type: 'agent',  // Sessions from history are always agent type
      status: 'active',
      created_at: new Date().toISOString()
    };

    setTabs(prev => {
      const newTabs = [...prev, newTab];
      saveWorkspaceInternal(newTabs, newTabs.length - 1, null, null);
      return newTabs;
    });

    setConnections(prev => ({
      ...prev,
      [tabId]: {
        state: 'idle',
        sessionId: sessionId,
        messages: [],
        currentMessage: null,
        stats: {},
        isProcessing: false,
        deepPlotReport: null
      }
    }));

    setActiveTabId(tabId);

    // Connect and resume session
    connectTab(tabId, sessionId);
  }, [connectTab, saveWorkspaceInternal]);

  // ========== New Tab (+ button) ==========

  const handleNewAgentTab = useCallback(() => {
    // Just set active to null - shows home page
    // Tab will be created when user sends first query
    setActiveTabId(null);

    setTabs(currentTabs => {
      saveWorkspaceInternal(currentTabs, null, null, null);
      return currentTabs;
    });
  }, [saveWorkspaceInternal]);

  // ========== Workspace ==========

  const handleWorkspaceLoaded = useCallback((data) => {
    if (workspaceLoadedRef.current) {
      return;  // Already loaded
    }
    workspaceLoadedRef.current = true;

    const loadedTabs = migrateWorkspace(data.workspace?.agent_tabs || []).map(tab => ({
      ...tab,
      type: tab.type || 'agent'  // Default to 'agent' for backwards compatibility
    }));
    console.log(`[useAgentConnections] Loading workspace with ${loadedTabs.length} tabs`);

    // Initialize all tabs and connections (skip MLE tabs - they don't need websocket)
    const newConnections = {};
    loadedTabs.forEach(tab => {
      if (tab.type !== 'mle') {
        newConnections[tab.tab_id] = {
          state: 'idle',
          sessionId: tab.session_id,
          messages: [],
          currentMessage: null,
          stats: {},
          isProcessing: false,
          deepPlotReport: null
        };
      }
    });

    setTabs(loadedTabs);
    setConnections(newConnections);

    // Set active tab
    const activeIdx = data.workspace?.active_agent_tab;
    let activeId = null;
    if (activeIdx !== null && activeIdx !== undefined && loadedTabs[activeIdx]) {
      activeId = loadedTabs[activeIdx].tab_id;
      setActiveTabId(activeId);
    }

    // Connect ALL tabs with session_id
    loadedTabs.forEach(tab => {
      if (tab.session_id) {
        // Use setTimeout to ensure state is updated before connecting
        setTimeout(() => {
          connectTab(tab.tab_id, tab.session_id);
        }, 0);
      }
    });

    // Notify App.jsx so usePlotTabs can also handle workspace
    onWorkspaceLoaded?.(data);
  }, [connectTab, onWorkspaceLoaded]);

  // ========== Fetch History When Needed ==========

  // When switching to a tab that has a session but no messages, fetch history
  useEffect(() => {
    if (!activeTabId) return;

    const conn = connections[activeTabId];
    const tab = tabs.find(t => t.tab_id === activeTabId);
    const ws = wsRefs.current[activeTabId];

    // Only fetch if:
    // 1. Tab has a session_id
    // 2. Connection exists but has no messages
    // 3. Not currently processing
    // 4. WebSocket is connected
    if (
      tab?.session_id &&
      conn &&
      conn.messages.length === 0 &&
      !conn.currentMessage &&
      !conn.isProcessing &&
      ws?.readyState === WebSocket.OPEN
    ) {
      console.log(`[useAgentConnections] Fetching history for tab ${activeTabId}`);
      ws.send(JSON.stringify({
        type: 'activate_session',
        session_id: tab.session_id
      }));
    }
  }, [activeTabId, connections, tabs]);

  // ========== Initial Control WebSocket for Workspace Loading ==========

  useEffect(() => {
    // Create control WebSocket to load workspace
    if (controlWsRef.current || controlConnectedRef.current) {
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    console.log('[useAgentConnections] Creating control WebSocket for workspace loading');

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[useAgentConnections] Control WebSocket connected');
      controlConnectedRef.current = true;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'workspace_loaded') {
          handleWorkspaceLoaded(data);
        }
      } catch (err) {
        console.error('[useAgentConnections] Error parsing control WebSocket message:', err);
      }
    };

    ws.onerror = (event) => {
      console.error('[useAgentConnections] Control WebSocket error:', event);
    };

    ws.onclose = () => {
      console.log('[useAgentConnections] Control WebSocket closed');
      controlConnectedRef.current = false;
    };

    controlWsRef.current = ws;

    // Cleanup on unmount
    return () => {
      if (controlWsRef.current) {
        controlWsRef.current.close();
        controlWsRef.current = null;
      }
    };
  }, [handleWorkspaceLoaded]);

  // ========== Cleanup on unmount ==========

  useEffect(() => {
    return () => {
      // Disconnect all tabs on unmount
      Object.keys(wsRefs.current).forEach(tabId => {
        disconnectTab(tabId);
      });

      // Close control WebSocket
      if (controlWsRef.current) {
        controlWsRef.current.close();
        controlWsRef.current = null;
      }

      // Clear save timeout
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, [disconnectTab]);

  // ========== Return ==========

  const activeConn = activeTabId ? connections[activeTabId] : null;

  // Debug logging for tab switching issues (skip MLE tabs - they don't need connections)
  const activeTab = tabs.find(t => t.tab_id === activeTabId);
  if (activeTabId && !activeConn && activeTab?.type !== 'mle') {
    console.warn(`[useAgentConnections] activeTabId=${activeTabId} but no connection found!`);
    console.warn(`[useAgentConnections] Available connections:`, Object.keys(connections));
  }

  const allMessages = activeConn
    ? [...(activeConn.messages || []), activeConn.currentMessage].filter(Boolean)
    : [];

  // Check if any WebSocket is connected (control or tab)
  const hasAnyConnection = controlConnectedRef.current ||
    Object.values(connections).some(c => c.state === 'connected');

  return {
    // Tab state
    tabs,
    activeTabId,
    activeTabIndex: tabs.findIndex(t => t.tab_id === activeTabId),

    // Active tab's state
    messages: allMessages,
    stats: activeConn?.stats || {},
    isProcessing: activeConn?.isProcessing || false,
    isConnected: hasAnyConnection,  // True if any connection is active
    currentSessionId: activeConn?.sessionId,
    deepPlotReport: activeConn?.deepPlotReport || null,

    // Tab management
    createTab,
    closeTab,
    switchToTab,
    renameTab,

    // Query
    sendQuery,
    sendDeepPlot,

    // Session switch (from history dropdown)
    handleSessionSwitch,

    // New tab button
    handleNewAgentTab,

    // Workspace
    handleWorkspaceLoaded,

    // Workspace save (for plot tabs to use)
    saveWorkspace: saveWorkspaceInternal,

    // For workspace persistence
    getWorkspaceState: () => ({
      agent_tabs: tabs,
      active_agent_tab: tabs.findIndex(t => t.tab_id === activeTabId)
    })
  };
}
