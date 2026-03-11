import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import Plot from 'react-plotly.js';
import { PlotTabs } from './PlotTabs';
import { SCREENSHOT_EVENTS } from '../config';

/**
 * Panel for displaying interactive Plotly plots.
 *
 * Renders Plotly plots directly (no iframe) for proper legend display.
 * Includes integrated resize handle on the left border.
 */
export function PlotPanel({
  plotUrl,
  onClose,
  tabs = [],
  activeTabIndex,
  onTabClick,
  onTabClose,
  onResize,
  onHideLeft,
  onHideRight,
  showButtons,
  onNewTab,
  currentSessionId,
  onSessionSwitch,
  plotCommand,
  cacheClearTrigger  // Increment to clear plotDataCache (used after plot renumbering)
}) {
  const [isLoading, setIsLoading] = useState(true);
  const [plotData, setPlotData] = useState(null);
  const [error, setError] = useState(null);
  const containerRef = useRef(null);
  const dragIndicatorRef = useRef(null);
  const plotRef = useRef(null);
  const pendingCommand = useRef(null);  // Store command to execute after plot renders
  const pendingStateRestore = useRef(null);  // Store view_state to restore after plot renders
  const isRestoringState = useRef(false);  // Flag to prevent logging during state restoration
  const plotDataCache = useRef(new Map());  // Cache: "sessionId/plotId" -> plotData (eliminates re-fetch on tab switch)

  // Clear cache when trigger changes (e.g., after plot renumbering)
  useEffect(() => {
    if (cacheClearTrigger > 0) {
      plotDataCache.current.clear();
      // Re-fetch current plot by clearing plotData (triggers useEffect below)
      setPlotData(null);
      setIsLoading(true);
    }
  }, [cacheClearTrigger]);

  // Parse session_id, plot_id, and version from plotUrl
  const parseUrl = useCallback((url) => {
    if (!url) return null;
    // URL format: /plot/{session_id}/{plot_id} or /plot/{session_id}/{plot_id}?v=timestamp
    const match = url.match(/\/plot\/([^/]+)\/(\d+)/);
    if (match) {
      // Extract version query param if present (for cache-busting)
      const versionMatch = url.match(/[?&]v=(\d+)/);
      const version = versionMatch ? versionMatch[1] : null;
      return { sessionId: match[1], plotId: parseInt(match[2], 10), version };
    }
    return null;
  }, []);

  // Fetch plot JSON when URL changes (with caching for instant tab switching)
  useEffect(() => {
    const parsed = parseUrl(plotUrl);
    if (!parsed) {
      setPlotData(null);
      setIsLoading(false);
      return;
    }

    // Cache key: "sessionId/plotId" (version is used to invalidate cache)
    const cacheKey = `${parsed.sessionId}/${parsed.plotId}`;

    // Check cache first (unless version param indicates update)
    // Version param means plot was updated - invalidate cache
    if (!parsed.version && plotDataCache.current.has(cacheKey)) {
      const cachedData = plotDataCache.current.get(cacheKey);
      // Restore view_state for state restoration
      if (cachedData.view_state) {
        pendingStateRestore.current = cachedData.view_state;
      }
      setPlotData(cachedData);
      setIsLoading(false);
      setError(null);
      return;
    }

    // Reset pending state when plot changes
    pendingStateRestore.current = null;
    setIsLoading(true);
    setError(null);

    // Build fetch URL with optional version for cache-busting
    const fetchUrl = parsed.version
      ? `/plot/api/json/${parsed.sessionId}/${parsed.plotId}?v=${parsed.version}`
      : `/plot/api/json/${parsed.sessionId}/${parsed.plotId}`;

    fetch(fetchUrl)
      .then(response => {
        if (!response.ok) {
          throw new Error(`Failed to load plot: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        // Store view_state for restoration after plot renders
        if (data.view_state) {
          pendingStateRestore.current = data.view_state;
        }
        // Store plot info WITH the data
        // This ensures handleAfterPlot uses the correct plot info for this specific render
        const enrichedData = {
          ...data,
          _plotInfo: { sessionId: parsed.sessionId, plotId: parsed.plotId }
        };

        // Cache the data for instant tab switching
        plotDataCache.current.set(cacheKey, enrichedData);

        setPlotData(enrichedData);
        setIsLoading(false);
        // Don't log init here - wait for onAfterPlot to capture screenshot
      })
      .catch(err => {
        console.error('Failed to fetch plot:', err);
        setError(err.message);
        setIsLoading(false);
      });
  }, [plotUrl, parseUrl]);

  // Capture screenshot using Plotly.toImage
  // If plotElement is provided, use it instead of plotRef (for capturing specific plot)
  const captureScreenshot = useCallback(async (plotElement = null) => {
    const el = plotElement || (plotRef.current && plotRef.current.el);
    if (!el) return null;
    try {
      // Access the Plotly instance from react-plotly.js
      const Plotly = window.Plotly;
      if (!Plotly) return null;

      const dataUrl = await Plotly.toImage(el, {
        format: 'png',
        width: 1200,
        height: 700,
        scale: 1
      });
      return dataUrl;
    } catch (err) {
      console.error('Failed to capture screenshot:', err);
      return null;
    }
  }, []);

  // Log event to server (with optional screenshot based on config)
  const logEvent = useCallback(async (sessionId, plotId, eventType, payload, forceScreenshot = null) => {
    try {
      // Capture screenshot if event type is in SCREENSHOT_EVENTS (unless already provided)
      let screenshot = forceScreenshot;
      if (screenshot === null && SCREENSHOT_EVENTS.includes(eventType)) {
        // Small delay to let plot update (e.g., after legendclick or relayout)
        await new Promise(resolve => setTimeout(resolve, 100));
        screenshot = await captureScreenshot();
      }

      await fetch('/plot/api/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          plot_id: plotId,
          timestamp: new Date().toISOString(),
          event_type: eventType,
          payload: payload,
          screenshot: screenshot
        })
      });
    } catch (err) {
      console.error('Failed to log event:', err);
    }
  }, [captureScreenshot]);

  // Execute a plot command (extracted for reuse)
  // Note: We don't log here - the regular event handlers (handleRelayout, handleLegendClick, etc.)
  // will capture and log the events automatically, preventing duplicate entries.
  const executeCommand = useCallback((command, parsed) => {
    if (!plotRef.current || !plotRef.current.el) return false;

    const Plotly = window.Plotly;
    if (!Plotly) return false;

    // Execute the command - event handlers will log automatically
    if (command.command === 'relayout') {
      Plotly.relayout(plotRef.current.el, command.args)
        .catch(err => {
          console.error('Failed to execute relayout command:', err);
        });
    } else if (command.command === 'legendclick') {
      // Toggle trace visibility
      // Note: Plotly.restyle doesn't trigger onLegendClick, so we log manually here
      const curveNumber = command.args.curve_number;
      const currentData = plotRef.current.el.data;
      if (curveNumber >= 0 && curveNumber < currentData.length) {
        const currentVisibility = currentData[curveNumber].visible;
        const newVisibility = currentVisibility === 'legendonly' ? true : 'legendonly';
        Plotly.restyle(plotRef.current.el, { visible: newVisibility }, [curveNumber])
          .then(() => {
            logEvent(parsed.sessionId, parsed.plotId, 'legendclick', {
              curve_number: curveNumber,
              visible: newVisibility
            });
          })
          .catch(err => {
            console.error('Failed to execute legendclick command:', err);
          });
      }
    } else if (command.command === 'selected') {
      // Create selection programmatically
      const { x_range, y_range, point_indices } = command.args;

      if (point_indices && point_indices.length > 0) {
        // Select specific points by indices
        // Note: Manual selection doesn't trigger onSelected, so we log manually
        const points = point_indices.map(idx => ({
          pointNumber: idx,
          curveNumber: 0  // Default to first trace
        }));
        Plotly.Fx.loneUnhover(plotRef.current.el);
        const eventData = { points };
        plotRef.current.el.emit('plotly_selected', eventData);
        logEvent(parsed.sessionId, parsed.plotId, 'selected', { point_indices });
      } else if (x_range || y_range) {
        // Select by range - use relayout (handleRelayout will log)
        const range = {};
        if (x_range) {
          range['xaxis.range'] = x_range;
        }
        if (y_range) {
          range['yaxis.range'] = y_range;
        }
        Plotly.relayout(plotRef.current.el, range)
          .catch(err => {
            console.error('Failed to execute selected command:', err);
          });
      }
    }
    return true;
  }, [logEvent]);

  // Handle agent-initiated plot commands (e.g., relayout, legendclick, selected)
  useEffect(() => {
    if (!plotCommand) return;

    const parsed = parseUrl(plotUrl);
    if (!parsed) return;

    // Only execute if command is for current plot
    if (plotCommand.sessionId !== parsed.sessionId || plotCommand.plotId !== parsed.plotId) {
      // Store as pending if this plot will be loaded
      pendingCommand.current = plotCommand;
      return;
    }

    // Try to execute now
    if (plotRef.current && plotRef.current.el) {
      executeCommand(plotCommand, parsed);
      pendingCommand.current = null;
    } else {
      // Plot not ready yet, store as pending
      pendingCommand.current = plotCommand;
    }
  }, [plotCommand, plotUrl, parseUrl, executeCommand]);

  // Restore plot state from view_state (without logging)
  const restoreState = useCallback((state) => {
    if (!plotRef.current || !plotRef.current.el || !state) return;

    const Plotly = window.Plotly;
    if (!Plotly) return;

    // Set flag to prevent logging during restoration
    isRestoringState.current = true;

    // Build relayout update from state
    const relayoutUpdate = {};

    // Restore axis ranges
    if (state['xaxis.range[0]'] !== undefined) {
      relayoutUpdate['xaxis.range[0]'] = state['xaxis.range[0]'];
    }
    if (state['xaxis.range[1]'] !== undefined) {
      relayoutUpdate['xaxis.range[1]'] = state['xaxis.range[1]'];
    }
    if (state['yaxis.range[0]'] !== undefined) {
      relayoutUpdate['yaxis.range[0]'] = state['yaxis.range[0]'];
    }
    if (state['yaxis.range[1]'] !== undefined) {
      relayoutUpdate['yaxis.range[1]'] = state['yaxis.range[1]'];
    }
    // Handle array format ranges
    if (state['xaxis.range']) {
      relayoutUpdate['xaxis.range'] = state['xaxis.range'];
    }
    if (state['yaxis.range']) {
      relayoutUpdate['yaxis.range'] = state['yaxis.range'];
    }

    // Apply relayout if there are axis changes
    const hasRelayoutChanges = Object.keys(relayoutUpdate).length > 0;
    if (hasRelayoutChanges) {
      Plotly.relayout(plotRef.current.el, relayoutUpdate)
        .catch(err => console.error('Failed to restore axis ranges:', err));
    }

    // Restore trace visibility
    if (state.trace_visibility && Object.keys(state.trace_visibility).length > 0) {
      const currentData = plotRef.current.el.data;
      Object.entries(state.trace_visibility).forEach(([curveStr, visible]) => {
        const curveNumber = parseInt(curveStr, 10);
        if (curveNumber >= 0 && curveNumber < currentData.length) {
          Plotly.restyle(plotRef.current.el, { visible }, [curveNumber])
            .catch(err => console.error('Failed to restore trace visibility:', err));
        }
      });
    }

    // Clear flag after a delay to allow all updates to complete
    setTimeout(() => {
      isRestoringState.current = false;
    }, 500);
  }, []);

  // Handle plot rendered - restore state and execute pending commands
  // Init screenshots are now captured server-side at plot creation time (using Kaleido)
  // This callback only handles: state restoration for resumed sessions and pending commands
  const handleAfterPlot = useCallback(() => {
    const plotInfo = plotData?._plotInfo;
    if (!plotInfo) return;

    // Restore view state if resuming a session
    if (pendingStateRestore.current) {
      const state = pendingStateRestore.current;
      const hasMeaningfulState = (
        state['xaxis.range[0]'] !== undefined ||
        state['yaxis.range[0]'] !== undefined ||
        state['xaxis.range'] !== undefined ||
        state['yaxis.range'] !== undefined ||
        (state.trace_visibility && Object.keys(state.trace_visibility).length > 0)
      );

      if (hasMeaningfulState) {
        setTimeout(() => {
          restoreState(state);
          pendingStateRestore.current = null;
        }, 300);
      } else {
        pendingStateRestore.current = null;
      }
    }

    // Execute any pending command (after a small delay to ensure DOM is ready)
    if (pendingCommand.current) {
      const cmd = pendingCommand.current;
      if (cmd.sessionId === plotInfo.sessionId && cmd.plotId === plotInfo.plotId) {
        setTimeout(() => {
          executeCommand(cmd, plotInfo);
        }, 200);
      }
      pendingCommand.current = null;
    }
  }, [plotData, executeCommand, restoreState]);

  // Plotly event handlers
  const handleClick = useCallback((data) => {
    const parsed = parseUrl(plotUrl);
    if (!parsed) return;

    const points = data.points.map(p => ({ x: p.x, y: p.y, curve: p.curveNumber }));
    logEvent(parsed.sessionId, parsed.plotId, 'click', { points });
  }, [plotUrl, parseUrl, logEvent]);

  const handleDoubleClick = useCallback(() => {
    const parsed = parseUrl(plotUrl);
    if (!parsed) return;
    logEvent(parsed.sessionId, parsed.plotId, 'doubleclick', { action: 'doubleclick' });
  }, [plotUrl, parseUrl, logEvent]);

  const handleSelected = useCallback((data) => {
    const parsed = parseUrl(plotUrl);
    if (!parsed || !data || !data.points || data.points.length === 0) return;

    logEvent(parsed.sessionId, parsed.plotId, 'selected', {
      point_count: data.points.length,
      range: data.range
    });
  }, [plotUrl, parseUrl, logEvent]);

  const handleLegendClick = useCallback((data) => {
    const parsed = parseUrl(plotUrl);
    if (!parsed) return;

    logEvent(parsed.sessionId, parsed.plotId, 'legendclick', {
      curve_number: data.curveNumber,
      expanded_index: data.expandedIndex
    });
    return true; // Allow default behavior
  }, [plotUrl, parseUrl, logEvent]);

  const handleRelayout = useCallback((data) => {
    const parsed = parseUrl(plotUrl);
    if (!parsed) return;

    // Skip logging during state restoration (resume)
    if (isRestoringState.current) return;

    // Only log significant relayout events (zoom, pan)
    if (data['xaxis.range[0]'] || data['xaxis.autorange'] || data['yaxis.range[0]']) {
      logEvent(parsed.sessionId, parsed.plotId, 'relayout', data);
    }
  }, [plotUrl, parseUrl, logEvent]);

  // Memoize Plot props to prevent unnecessary re-renders during resize
  // Remove width/height from layout to allow autosize to work properly
  const plotLayout = useMemo(() => {
    if (!plotData?.layout) return { autosize: true };
    // eslint-disable-next-line no-unused-vars
    const { width, height, ...layoutWithoutSize } = plotData.layout;
    return {
      ...layoutWithoutSize,
      autosize: true,
    };
  }, [plotData?.layout]);

  const plotConfig = useMemo(() => ({
    responsive: true,
    displayModeBar: true,
  }), []);

  const plotStyle = useMemo(() => ({
    width: '100%',
    height: '100%'
  }), []);

  const handleMouseDown = (e) => {
    e.preventDefault();
    e.stopPropagation();

    // Use DOM manipulation for drag indicator instead of React state
    if (dragIndicatorRef.current) {
      dragIndicatorRef.current.classList.add('bg-blue-400');
      dragIndicatorRef.current.classList.remove('bg-transparent', 'group-hover:bg-blue-200');
    }

    // Find both panels
    const chatPanel = document.querySelector('.chat-panel');
    const plotPanel = e.currentTarget.closest('.border-l');
    if (!chatPanel) return;

    // Disable transitions and enable GPU acceleration
    chatPanel.style.cssText += 'transition: none !important; will-change: width;';
    if (plotPanel) {
      plotPanel.style.cssText += 'will-change: contents;';
    }

    let lastPercentage = null;
    let animationFrameId = null;
    let lastResizeDispatch = 0;

    const handleMouseMove = (moveEvent) => {
      moveEvent.preventDefault();

      // Cancel previous frame if still pending
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }

      // Schedule update for next frame
      animationFrameId = requestAnimationFrame(() => {
        const containerWidth = window.innerWidth;
        const mouseX = moveEvent.clientX;
        const newPercentage = (mouseX / containerWidth) * 100;
        const constrainedPercentage = Math.min(Math.max(newPercentage, 15), 85);

        // Direct DOM manipulation
        chatPanel.style.width = `${constrainedPercentage}%`;
        lastPercentage = constrainedPercentage;

        // Throttled resize event dispatch during drag (every 100ms)
        const now = Date.now();
        if (now - lastResizeDispatch > 100) {
          window.dispatchEvent(new Event('resize'));
          lastResizeDispatch = now;
        }
      });
    };

    const cleanup = () => {
      // Reset drag indicator via DOM manipulation
      if (dragIndicatorRef.current) {
        dragIndicatorRef.current.classList.remove('bg-blue-400');
        dragIndicatorRef.current.classList.add('bg-transparent', 'group-hover:bg-blue-200');
      }

      // Cancel any pending frame
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }

      // Restore transitions and remove will-change
      chatPanel.style.cssText = chatPanel.style.cssText.replace('transition: none !important; will-change: width;', '');
      if (plotPanel) {
        plotPanel.style.cssText = plotPanel.style.cssText.replace('will-change: contents;', '');
      }

      // Dispatch resize event to ensure Plotly knows the current size
      window.dispatchEvent(new Event('resize'));

      // Delay React state update until after Plotly has processed the resize
      // This prevents the "shrink then grow" visual flash
      setTimeout(() => {
        // Commit final position to React state
        if (onResize && lastPercentage !== null) {
          onResize(lastPercentage);
        }
        // Final resize event after React re-render settles
        setTimeout(() => {
          window.dispatchEvent(new Event('resize'));
        }, 50);
      }, 100);

      // Remove all listeners
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', cleanup);
      document.removeEventListener('mouseleave', cleanup);
    };

    // Use both mouseup and mouseleave as safeguards
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', cleanup);
    document.addEventListener('mouseleave', cleanup);
  };

  // Show empty placeholder if no tabs
  if (tabs.length === 0) {
    return (
      <div className="flex flex-col h-full bg-white border-l border-gray-200">
        <div className="flex items-center justify-center flex-1 text-gray-400 text-sm">
          No plots to display
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex flex-col h-full bg-white border-l border-gray-200">
      {/* Integrated Resize Handle - overlays the left border */}
      {/* Uses CSS hover and refs instead of React state to avoid triggering Plotly re-renders */}
      {onResize && (
        <div
          className="absolute left-0 top-0 h-full w-3 cursor-col-resize z-20 group"
          onMouseDown={handleMouseDown}
        >
          {/* Subtle hover/drag highlight - uses CSS group-hover and ref for drag state */}
          <div
            ref={dragIndicatorRef}
            className="absolute left-0 top-0 h-full w-1 transition-colors duration-200 bg-transparent group-hover:bg-blue-200"
          />
        </div>
      )}

      {/* Tab Strip */}
      <PlotTabs
        tabs={tabs}
        activeTabIndex={activeTabIndex}
        onTabClick={onTabClick}
        onTabClose={onTabClose}
        showButtons={showButtons}
        onNewTab={onNewTab}
        currentSessionId={currentSessionId}
        onSessionSwitch={onSessionSwitch}
      />

      {/* Plot Content */}
      <div ref={containerRef} className="flex-1 relative overflow-hidden">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50 z-10">
            <div className="text-gray-400 text-sm">Loading plot...</div>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50">
            <div className="text-red-500 text-sm">{error}</div>
          </div>
        )}

        {plotData && !error && (
          <Plot
            ref={plotRef}
            data={plotData.data}
            layout={plotLayout}
            config={plotConfig}
            style={plotStyle}
            useResizeHandler={true}
            onClick={handleClick}
            onDoubleClick={handleDoubleClick}
            onSelected={handleSelected}
            onLegendClick={handleLegendClick}
            onRelayout={handleRelayout}
            onAfterPlot={handleAfterPlot}
          />
        )}

        {!plotData && !isLoading && !error && (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            No plot selected
          </div>
        )}
      </div>
    </div>
  );
}
