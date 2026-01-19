import { useState, useCallback } from 'react';

/**
 * Custom hook for managing plot tabs.
 *
 * Handles:
 * - Plot tab state (tabs and active index)
 * - Creating new plot tabs from WebSocket
 * - Closing plot tabs
 * - Switching between plot tabs
 * - Loading workspace plots
 *
 * @param {Object} currentSessionId - Current session ID
 * @param {Function} saveWorkspace - Function to save workspace to backend
 * @param {Boolean} userHasAdjustedWidth - Whether user manually adjusted panel width
 * @param {Function} setChatWidth - Function to set chat panel width
 * @param {Function} setPlotUrl - Function to set current plot URL
 * @param {Function} setPlotVisible - Function to set plot visibility
 * @returns {Object} Plot tabs state and handlers
 */
export function usePlotTabs(
  currentSessionId,
  saveWorkspace,
  userHasAdjustedWidth,
  setChatWidth,
  setPlotUrl,
  setPlotVisible
) {
  const [tabs, setTabs] = useState([]);
  const [activeTabIndex, setActiveTabIndex] = useState(null);

  /**
   * Handle plot_show WebSocket message.
   * Creates new tab for plot or activates existing one.
   * Uses functional setState to avoid stale closure issues with rapid events.
   */
  const handlePlotShow = useCallback((data) => {
    if (data.url && data.plot_id) {
      console.log('[usePlotTabs] handlePlotShow:', data.plot_id, data.session_id);
      // Extract plot type from URL or default to 'plot'
      const plotType = data.plot_type || 'plot';
      // Add timestamp to URL for cache-busting on updates
      const plotUrlWithVersion = `${data.url}?v=${Date.now()}`;

      // Use functional form to access latest tabs state
      setTabs(prevTabs => {
        console.log('[usePlotTabs] setTabs prevTabs:', prevTabs.map(t => t.plot_id));
        // Check if tab already exists (by session_id + plot_id)
        const existingTabIndex = prevTabs.findIndex(
          t => t.plot_id === data.plot_id && t.session_id === data.session_id
        );

        if (existingTabIndex >= 0) {
          // Tab exists - check if this is an update (data.updated flag)
          if (data.updated) {
            // Plot was updated - update the tab's URL to force refetch
            const updatedTabs = [...prevTabs];
            updatedTabs[existingTabIndex] = {
              ...updatedTabs[existingTabIndex],
              plot_url: plotUrlWithVersion
            };
            setActiveTabIndex(existingTabIndex);
            setPlotUrl(plotUrlWithVersion);
            return updatedTabs;
          }
          // Just activate existing tab (no update)
          setActiveTabIndex(existingTabIndex);
          setPlotUrl(prevTabs[existingTabIndex].plot_url);
          return prevTabs;  // No change to tabs
        }

        // Create new tab with session_id and session_name
        const newTab = {
          plot_id: data.plot_id,
          session_id: data.session_id,
          session_name: data.session_name || 'Agent',  // Store name directly
          plot_type: plotType,
          plot_url: data.url,
          created_at: new Date().toISOString()
        };

        let newTabs = [...prevTabs, newTab];

        // Auto-remove first tab if limit reached
        if (newTabs.length > 30) {
          console.log('Tab limit reached. Removing oldest tab to make space.');
          newTabs = newTabs.slice(1);
        }

        const newActiveIndex = newTabs.length - 1;

        setActiveTabIndex(newActiveIndex);
        setPlotUrl(data.url);

        // Save workspace (null for agent tabs - we only update plot tabs)
        saveWorkspace(null, null, newTabs, newActiveIndex);

        return newTabs;
      });

      setPlotVisible(true);
      // Set default 1:3 ratio (25% chat, 75% plot) if user hasn't manually adjusted
      if (!userHasAdjustedWidth) {
        setChatWidth(25);
      }
    }
  }, [saveWorkspace, userHasAdjustedWidth, setChatWidth, setPlotUrl, setPlotVisible]);

  /**
   * Handle workspace_loaded WebSocket message.
   * Loads global workspace (plot tabs persist across all sessions).
   */
  const handleWorkspaceLoaded = useCallback((data) => {
    if (data.workspace && data.workspace.plot_tabs) {
      const loadedTabs = data.workspace.plot_tabs;

      // Global workspace contains full tab objects with plot_url already set
      setTabs(loadedTabs);

      // Set active tab
      const activeIdx = data.workspace.active_plot_tab;
      if (activeIdx !== null && activeIdx >= 0 && activeIdx < loadedTabs.length) {
        setActiveTabIndex(activeIdx);
        setPlotUrl(loadedTabs[activeIdx].plot_url);
        setPlotVisible(true);
        if (!userHasAdjustedWidth) {
          setChatWidth(25);
        }
      } else {
        setActiveTabIndex(null);
        setPlotUrl(null);
        setPlotVisible(false);
      }
    }
  }, [userHasAdjustedWidth, setChatWidth, setPlotUrl, setPlotVisible]);

  /**
   * Handle clicking on a plot tab.
   * Activates that tab and shows its plot.
   */
  const handleTabClick = useCallback((index) => {
    if (index >= 0 && index < tabs.length) {
      setActiveTabIndex(index);
      setPlotUrl(tabs[index].plot_url);
      setPlotVisible(true);

      // Save workspace with new active tab (null for agent tabs)
      saveWorkspace(null, null, tabs, index);
    }
  }, [tabs, saveWorkspace, setPlotUrl, setPlotVisible]);

  /**
   * Handle closing a plot tab.
   * Removes tab and adjusts active index appropriately.
   */
  const handleTabClose = useCallback((index) => {
    if (index < 0 || index >= tabs.length) return;

    const newTabs = tabs.filter((_, i) => i !== index);

    if (newTabs.length === 0) {
      // No tabs left
      setTabs([]);
      setActiveTabIndex(null);
      setPlotUrl(null);
      setPlotVisible(false);
      saveWorkspace(null, null, [], null);
    } else {
      // Update active tab index
      let newActiveIndex;
      if (index === activeTabIndex) {
        // Closing active tab - activate previous tab or first tab
        newActiveIndex = index > 0 ? index - 1 : 0;
      } else if (index < activeTabIndex) {
        // Closing tab before active - adjust active index
        newActiveIndex = activeTabIndex - 1;
      } else {
        // Closing tab after active - keep active index
        newActiveIndex = activeTabIndex;
      }

      setTabs(newTabs);
      setActiveTabIndex(newActiveIndex);
      setPlotUrl(newTabs[newActiveIndex].plot_url);

      // Save workspace (null for agent tabs)
      saveWorkspace(null, null, newTabs, newActiveIndex);
    }
  }, [tabs, activeTabIndex, saveWorkspace, setPlotUrl, setPlotVisible]);

  /**
   * Handle close plot (X button - closes active tab).
   * Helper function that closes the currently active tab.
   */
  const handleClosePlot = useCallback(() => {
    if (activeTabIndex !== null && tabs.length > 0) {
      handleTabClose(activeTabIndex);
    } else {
      // Fallback: close all
      setPlotUrl(null);
      setPlotVisible(false);
      setTabs([]);
      setActiveTabIndex(null);
      saveWorkspace(null, null, [], null);
    }
  }, [activeTabIndex, tabs.length, handleTabClose, setPlotUrl, setPlotVisible, saveWorkspace]);

  /**
   * Filter tabs to only show evidence plots.
   * Closes all tabs not in the evidence list and activates the first evidence plot.
   * @param {number[]} evidencePlotIds - List of plot IDs to keep
   * @param {string} sessionId - Session ID to filter by (optional)
   */
  const filterToEvidencePlots = useCallback((evidencePlotIds, sessionId = null) => {
    if (!evidencePlotIds || evidencePlotIds.length === 0) {
      return;
    }

    // Filter tabs to only those in evidence list (optionally filter by session)
    const evidenceTabs = tabs.filter(tab => {
      const isEvidence = evidencePlotIds.includes(tab.plot_id);
      const matchesSession = sessionId ? tab.session_id === sessionId : true;
      return isEvidence && matchesSession;
    });

    if (evidenceTabs.length === 0) {
      // No evidence tabs found, hide plot panel
      setTabs([]);
      setActiveTabIndex(null);
      setPlotUrl(null);
      setPlotVisible(false);
      saveWorkspace(null, null, [], null);
      return;
    }

    // Set tabs to only evidence tabs, activate first one
    setTabs(evidenceTabs);
    setActiveTabIndex(0);
    setPlotUrl(evidenceTabs[0].plot_url);
    setPlotVisible(true);

    // Save workspace
    saveWorkspace(null, null, evidenceTabs, 0);
  }, [tabs, saveWorkspace, setPlotUrl, setPlotVisible]);

  /**
   * Sync plot tabs from backend API.
   * Fetches actual plots from server and ensures tabs match reality.
   * This is the self-healing mechanism for lost WebSocket events.
   *
   * @param {string} sessionId - Session ID to sync plots for
   */
  const syncPlotsFromBackend = useCallback(async (sessionId) => {
    if (!sessionId) return;

    console.log('[usePlotTabs] syncPlotsFromBackend:', sessionId);

    try {
      const response = await fetch(`/api/plots/${sessionId}`);
      if (!response.ok) {
        console.error('[usePlotTabs] Failed to fetch plots:', response.status);
        return;
      }

      const data = await response.json();
      const backendPlots = data.plots || [];
      const sessionName = data.session_name || 'Agent';

      console.log('[usePlotTabs] Backend plots:', backendPlots.map(p => p.plot_id));

      setTabs(prevTabs => {
        console.log('[usePlotTabs] Current tabs:', prevTabs.map(t => `${t.session_id}:${t.plot_id}`));

        // Separate tabs: this session vs other sessions
        const otherSessionTabs = prevTabs.filter(t => t.session_id !== sessionId);
        const thisSessionTabs = prevTabs.filter(t => t.session_id === sessionId);

        // Build set of existing plot_ids for this session
        const existingPlotIds = new Set(thisSessionTabs.map(t => t.plot_id));
        const backendPlotIds = new Set(backendPlots.map(p => p.plot_id));

        // Find missing plots (in backend but not in tabs)
        const missingPlots = backendPlots.filter(p => !existingPlotIds.has(p.plot_id));

        // Find extra tabs (in tabs but not in backend - deleted during finalization)
        const validSessionTabs = thisSessionTabs.filter(t => backendPlotIds.has(t.plot_id));

        if (missingPlots.length === 0 && validSessionTabs.length === thisSessionTabs.length) {
          console.log('[usePlotTabs] Tabs are in sync, no changes needed');
          return prevTabs;
        }

        console.log('[usePlotTabs] Missing plots:', missingPlots.map(p => p.plot_id));
        console.log('[usePlotTabs] Removed tabs:', thisSessionTabs.length - validSessionTabs.length);

        // Create tabs for missing plots
        const newTabs = missingPlots.map(p => ({
          plot_id: p.plot_id,
          session_id: sessionId,
          session_name: sessionName,
          plot_type: p.plot_type || 'plot',
          plot_url: `/plot/${sessionId}/${p.plot_id}?v=${Date.now()}`,
          created_at: new Date().toISOString()
        }));

        // Combine: other sessions + valid this session tabs + new tabs
        const allTabs = [...otherSessionTabs, ...validSessionTabs, ...newTabs];

        // Sort tabs for this session by plot_id
        allTabs.sort((a, b) => {
          if (a.session_id !== sessionId && b.session_id !== sessionId) return 0;
          if (a.session_id !== sessionId) return -1;
          if (b.session_id !== sessionId) return 1;
          return a.plot_id - b.plot_id;
        });

        // Update active tab
        if (allTabs.length > 0) {
          // Find first tab from this session, or just first tab
          const sessionTabIndex = allTabs.findIndex(t => t.session_id === sessionId);
          const newActiveIndex = sessionTabIndex >= 0 ? sessionTabIndex : 0;
          setActiveTabIndex(newActiveIndex);
          setPlotUrl(allTabs[newActiveIndex].plot_url);
          setPlotVisible(true);
          saveWorkspace(null, null, allTabs, newActiveIndex);
        } else {
          setActiveTabIndex(null);
          setPlotUrl(null);
          setPlotVisible(false);
          saveWorkspace(null, null, [], null);
        }

        return allTabs;
      });
    } catch (error) {
      console.error('[usePlotTabs] Error syncing plots:', error);
    }
  }, [saveWorkspace, setPlotUrl, setPlotVisible]);

  /**
   * Handle plot renumbering after submit_summary.
   * Updates tab plot_ids and URLs based on id_mapping, removes non-evidence tabs.
   *
   * @param {Object} idMapping - Mapping of old_id -> new_id (e.g., {4: 1, 5: 2, 6: 3})
   * @param {Array} finalPlotIds - Final plot IDs after renumbering (e.g., [1, 2, 3])
   * @param {string} sessionId - Session ID to filter by
   */
  const handlePlotsRenumbered = useCallback((idMapping, finalPlotIds, sessionId) => {
    if (!idMapping || Object.keys(idMapping).length === 0) {
      return;
    }

    // Convert idMapping keys to integers (JSON serialization converts them to strings)
    const mapping = {};
    for (const [oldId, newId] of Object.entries(idMapping)) {
      mapping[parseInt(oldId, 10)] = newId;
    }

    setTabs(prevTabs => {
      // Filter to only tabs from this session that are in the id_mapping (evidence plots)
      const updatedTabs = prevTabs
        .filter(tab => {
          // Keep tabs from other sessions unchanged
          if (tab.session_id !== sessionId) return true;
          // For this session, only keep tabs that are in mapping (evidence plots)
          return mapping.hasOwnProperty(tab.plot_id);
        })
        .map(tab => {
          // Update tabs from this session with new IDs
          if (tab.session_id !== sessionId) return tab;

          const oldId = tab.plot_id;
          const newId = mapping[oldId];
          if (newId === undefined) return tab;

          // Update plot_id and plot_url with new ID
          // Add version param to force cache-busting on fetch
          const baseUrl = `/plot/${sessionId}/${newId}`;
          const newUrl = `${baseUrl}?v=${Date.now()}`;

          return {
            ...tab,
            plot_id: newId,
            plot_url: newUrl
          };
        });

      // Sort tabs by new plot_id (for this session)
      updatedTabs.sort((a, b) => {
        if (a.session_id !== sessionId && b.session_id !== sessionId) return 0;
        if (a.session_id !== sessionId) return -1;
        if (b.session_id !== sessionId) return 1;
        return a.plot_id - b.plot_id;
      });

      // Update active tab if needed
      if (updatedTabs.length > 0) {
        const newActiveIndex = 0;
        setActiveTabIndex(newActiveIndex);
        setPlotUrl(updatedTabs[newActiveIndex].plot_url);
        saveWorkspace(null, null, updatedTabs, newActiveIndex);
      } else {
        setActiveTabIndex(null);
        setPlotUrl(null);
        setPlotVisible(false);
        saveWorkspace(null, null, [], null);
      }

      return updatedTabs;
    });
  }, [saveWorkspace, setPlotUrl, setPlotVisible]);

  return {
    tabs,
    activeTabIndex,
    setTabs,
    setActiveTabIndex,
    handlePlotShow,
    handleWorkspaceLoaded,
    handleTabClick,
    handleTabClose,
    handleClosePlot,
    filterToEvidencePlots,
    handlePlotsRenumbered,
    syncPlotsFromBackend
  };
}
