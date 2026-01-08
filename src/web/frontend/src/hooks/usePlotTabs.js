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
      // Extract plot type from URL or default to 'plot'
      const plotType = data.plot_type || 'plot';

      // Use functional form to access latest tabs state
      setTabs(prevTabs => {
        // Check if tab already exists (by session_id + plot_id)
        const existingTabIndex = prevTabs.findIndex(
          t => t.plot_id === data.plot_id && t.session_id === data.session_id
        );

        if (existingTabIndex >= 0) {
          // Tab exists, just activate it
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
    filterToEvidencePlots
  };
}
