"""
Headless plot command handler.

Handles plot commands (init, relayout, legendclick, selected) when no browser is connected.
Uses kaleido for server-side screenshot generation.

In browser mode, the browser captures init screenshot when plot first renders.
In headless mode, this handler generates the init event and screenshot.
"""

import json
from pathlib import Path
from typing import Any, Optional

import plotly.graph_objects as go

from ....core.session_registry import get_session_store
from ....utils.logging import create_logger
from ....utils.paths import get_logs_root

logger = create_logger(__name__)


class HeadlessHandler:
    """
    Handles plot commands server-side when no browser is connected.

    This provides the same functionality as browser-based interaction:
    - Generates init screenshot when plot is created
    - Updates plot JSON with new state
    - Generates screenshot using kaleido
    - Logs interaction to database with view_state
    """

    def __init__(self, logs_root: Path = None):
        self.logs_root = logs_root or get_logs_root()

    def handle_init(
        self,
        session_id: str,
        plot_id: int,
    ) -> dict:
        """
        Handle plot initialization - generate init event with screenshot.

        This matches browser behavior where init event is logged when plot first renders.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier

        Returns:
            Dict with interaction_id and status
        """
        logger.info(f"Headless handler: init on plot {plot_id} (session: {session_id})")

        try:
            # 1. Load plot JSON
            plot_json = self._load_plot_json(session_id, plot_id)
            if not plot_json:
                logger.error(f"Plot {plot_id} not found for session {session_id}")
                return {"success": False, "error": "Plot not found"}

            # 2. Log init interaction to database
            session_store = get_session_store(self.logs_root)
            interaction_id = session_store.log_interaction(
                session_id=session_id,
                plot_id=plot_id,
                event_type='init',
                payload={},  # Init has empty payload
            )

            # 3. Generate screenshot using kaleido (use interaction_id for filename)
            screenshot_path, screenshot_size_kb = self._generate_screenshot(
                session_id, plot_id, interaction_id, plot_json
            )

            # 4. Update interaction with screenshot info
            if screenshot_path:
                session_store.update_interaction_screenshot(
                    session_id=session_id,
                    plot_id=plot_id,
                    interaction_id=interaction_id,
                    screenshot_path=screenshot_path,
                    screenshot_size_kb=screenshot_size_kb
                )

            logger.info(f"Headless init complete: interaction_id={interaction_id}, screenshot={screenshot_path}")

            return {
                "success": True,
                "interaction_id": interaction_id,
                "screenshot_path": screenshot_path
            }

        except Exception as e:
            logger.error(f"Headless init error: {e}")
            return {"success": False, "error": str(e)}

    def handle_command(
        self,
        session_id: str,
        plot_id: int,
        command: str,
        args: dict[str, Any]
    ) -> dict:
        """
        Handle a plot command server-side.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier
            command: Command type ('relayout', 'legendclick', 'selected')
            args: Command arguments

        Returns:
            Dict with interaction_id and status
        """
        logger.info(f"Headless handler: {command} on plot {plot_id} (session: {session_id})")

        try:
            # 1. Load plot JSON
            plot_json = self._load_plot_json(session_id, plot_id)
            if not plot_json:
                logger.error(f"Plot {plot_id} not found for session {session_id}")
                return {"success": False, "error": "Plot not found"}

            # 2. Apply command to plot JSON
            updated_json = self._apply_command(plot_json, command, args)

            # 3. Save updated plot JSON
            self._save_plot_json(session_id, plot_id, updated_json)

            # 4. Build payload for logging (match browser format)
            payload = self._build_payload(command, args)

            # 5. Log interaction to database
            session_store = get_session_store(self.logs_root)
            interaction_id = session_store.log_interaction(
                session_id=session_id,
                plot_id=plot_id,
                event_type=command,
                payload=payload,
            )

            # 6. Generate screenshot using kaleido (use interaction_id for filename)
            screenshot_path, screenshot_size_kb = self._generate_screenshot(
                session_id, plot_id, interaction_id, updated_json
            )

            # 7. Update interaction with screenshot info
            if screenshot_path:
                session_store.update_interaction_screenshot(
                    session_id=session_id,
                    plot_id=plot_id,
                    interaction_id=interaction_id,
                    screenshot_path=screenshot_path,
                    screenshot_size_kb=screenshot_size_kb
                )

            logger.info(f"Headless handler complete: interaction_id={interaction_id}, screenshot={screenshot_path}")

            return {
                "success": True,
                "interaction_id": interaction_id,
                "screenshot_path": screenshot_path
            }

        except Exception as e:
            logger.error(f"Headless handler error: {e}")
            return {"success": False, "error": str(e)}

    def _load_plot_json(self, session_id: str, plot_id: int) -> Optional[dict]:
        """Load plot JSON from disk."""
        session_store = get_session_store(self.logs_root)
        session_folder = session_store._get_session_folder(session_id)
        plot_file = session_folder / "plots" / f"{plot_id}.json"

        if not plot_file.exists():
            return None

        with open(plot_file, 'r') as f:
            return json.load(f)

    def _save_plot_json(self, session_id: str, plot_id: int, plot_json: dict):
        """Save updated plot JSON to disk."""
        session_store = get_session_store(self.logs_root)
        session_folder = session_store._get_session_folder(session_id)
        plot_file = session_folder / "plots" / f"{plot_id}.json"

        with open(plot_file, 'w') as f:
            json.dump(plot_json, f, indent=2)

    def _apply_command(self, plot_json: dict, command: str, args: dict) -> dict:
        """
        Apply command to plot JSON, updating the figure state.

        Returns updated plot JSON.
        """
        if command == 'relayout':
            return self._apply_relayout(plot_json, args)
        elif command == 'legendclick':
            return self._apply_legendclick(plot_json, args)
        elif command == 'selected':
            return self._apply_selected(plot_json, args)
        else:
            logger.warning(f"Unknown command: {command}")
            return plot_json

    def _apply_relayout(self, plot_json: dict, args: dict) -> dict:
        """Apply relayout (zoom/pan) to plot JSON."""
        layout = plot_json.get('layout', {})

        # Handle axis range updates
        if 'xaxis.range[0]' in args and 'xaxis.range[1]' in args:
            if 'xaxis' not in layout:
                layout['xaxis'] = {}
            layout['xaxis']['range'] = [args['xaxis.range[0]'], args['xaxis.range[1]']]
            # Remove autorange if setting explicit range
            layout['xaxis'].pop('autorange', None)

        if 'yaxis.range[0]' in args and 'yaxis.range[1]' in args:
            if 'yaxis' not in layout:
                layout['yaxis'] = {}
            layout['yaxis']['range'] = [args['yaxis.range[0]'], args['yaxis.range[1]']]
            layout['yaxis'].pop('autorange', None)

        # Handle autorange reset
        if args.get('xaxis.autorange'):
            if 'xaxis' not in layout:
                layout['xaxis'] = {}
            layout['xaxis']['autorange'] = True
            layout['xaxis'].pop('range', None)

        if args.get('yaxis.autorange'):
            if 'yaxis' not in layout:
                layout['yaxis'] = {}
            layout['yaxis']['autorange'] = True
            layout['yaxis'].pop('range', None)

        plot_json['layout'] = layout
        return plot_json

    def _apply_legendclick(self, plot_json: dict, args: dict) -> dict:
        """Apply legendclick (toggle trace visibility) to plot JSON."""
        curve_number = args.get('curve_number', 0)
        data = plot_json.get('data', [])

        if 0 <= curve_number < len(data):
            trace = data[curve_number]
            # Toggle visibility: True -> 'legendonly', 'legendonly' -> True, None -> 'legendonly'
            current = trace.get('visible', True)
            if current == 'legendonly':
                trace['visible'] = True
            else:
                trace['visible'] = 'legendonly'

        return plot_json

    def _apply_selected(self, plot_json: dict, args: dict) -> dict:
        """Apply selection to plot JSON."""
        # Selection is typically a view state, not a data change
        # For headless mode, we treat it similar to relayout (zoom to selection)
        layout = plot_json.get('layout', {})

        if 'x_range' in args:
            x_range = args['x_range']
            if 'xaxis' not in layout:
                layout['xaxis'] = {}
            layout['xaxis']['range'] = x_range
            layout['xaxis'].pop('autorange', None)

        if 'y_range' in args:
            y_range = args['y_range']
            if 'yaxis' not in layout:
                layout['yaxis'] = {}
            layout['yaxis']['range'] = y_range
            layout['yaxis'].pop('autorange', None)

        plot_json['layout'] = layout
        return plot_json

    def _build_payload(self, command: str, args: dict) -> dict:
        """Build payload dict matching browser format."""
        payload = {}

        if command == 'relayout':
            # Copy relayout args directly (matches browser format)
            payload.update(args)
        elif command == 'legendclick':
            payload['curveNumber'] = args.get('curve_number', 0)
        elif command == 'selected':
            if 'x_range' in args:
                payload['range'] = {
                    'x': args.get('x_range'),
                    'y': args.get('y_range')
                }

        return payload

    def _generate_screenshot(
        self,
        session_id: str,
        plot_id: int,
        interaction_id: int,
        plot_json: dict
    ) -> tuple[Optional[str], Optional[int]]:
        """
        Generate screenshot using kaleido.

        Returns:
            Tuple of (relative_screenshot_path, size_kb) or (None, None) on failure
        """
        try:
            # Create figure from JSON
            fig = go.Figure(plot_json)

            # Ensure screenshots directory exists (organized by plot_id)
            session_store = get_session_store(self.logs_root)
            session_folder = session_store._get_session_folder(session_id)
            screenshots_dir = session_folder / "screenshots" / str(plot_id)
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            # Generate screenshot with kaleido (named by interaction_id)
            screenshot_file = screenshots_dir / f"{interaction_id}.png"
            fig.write_image(
                str(screenshot_file),
                format='png',
                width=800,
                height=600,
                scale=2  # 2x for retina-quality
            )

            # Get file size
            size_bytes = screenshot_file.stat().st_size
            size_kb = size_bytes // 1024

            # Return relative path (from session folder)
            relative_path = f"screenshots/{plot_id}/{interaction_id}.png"

            logger.debug(f"Screenshot generated: {relative_path} ({size_kb}KB)")
            return relative_path, size_kb

        except Exception as e:
            logger.error(f"Failed to generate screenshot: {e}")
            return None, None


# Singleton instance
_headless_handler: Optional[HeadlessHandler] = None


def get_headless_handler(logs_root: Path = None) -> HeadlessHandler:
    """Get or create singleton headless handler."""
    global _headless_handler
    if _headless_handler is None:
        _headless_handler = HeadlessHandler(logs_root)
    return _headless_handler
