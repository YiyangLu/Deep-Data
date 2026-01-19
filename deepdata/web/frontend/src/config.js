/**
 * Frontend configuration for plot event handling.
 */

/**
 * Events that should trigger screenshot capture.
 *
 * Available events:
 * - 'init'        - Plot first rendered (recommended: always capture)
 * - 'legendclick' - User toggles trace visibility
 * - 'relayout'    - User zooms or pans
 * - 'selected'    - User selects data with box/lasso
 * - 'click'       - User clicks on data point (no visual change)
 * - 'doubleclick' - User double-clicks (resets zoom)
 *
 * Note: hover/unhover events are not supported (too high frequency)
 */
export const SCREENSHOT_EVENTS = [
  'init',        // Initial plot state
  'legendclick', // Trace visibility changed
  'relayout',    // Zoom/pan shows user focus
  'selected',    // Data selection
];

/**
 * Events that are logged to database (with or without screenshot).
 * Screenshot is captured only if event is also in SCREENSHOT_EVENTS.
 */
export const LOGGED_EVENTS = [
  'init',
  'click',
  'doubleclick',
  'selected',
  'legendclick',
  'relayout',
];
