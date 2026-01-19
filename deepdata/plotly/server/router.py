"""
Plotly Router for Single Server Architecture

Clean API endpoints that delegate to service layer:
- plot_service: Plot storage and retrieval
- event_service: Event logging to database
- screenshot_service: Screenshot management

Mounts at /plot prefix in main web server.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .services import get_plot_store, EventService, ScreenshotService
from ...utils.logging import create_logger
from ...utils.paths import get_logs_root
from ...core.event_bus import get_event_bus

logger = create_logger(__name__)


# ============================================================
# Helper Functions
# ============================================================

def _load_plot_figure(session_id: str, plot_id: int):
    """
    Load plot figure from memory or disk.

    This is the single source of truth for plot loading:
    1. Try PlotStore (memory) first
    2. Fall back to SessionStore (disk)
    3. Cache to memory after disk load

    Returns:
        tuple: (fig, source) where source is 'memory', 'disk', or None if not found
    """
    import plotly.io as pio
    from ...core.session_registry import get_session_store

    # Try memory first
    if plot_store.exists(session_id, plot_id):
        fig = plot_store.get_plot(session_id, plot_id)
        logger.debug(f"Loaded plot {plot_id} from memory (session: {session_id})")
        return fig, 'memory'

    # Fall back to disk
    try:
        session_store = get_session_store(get_logs_root())
        fig_json = session_store.get_plot_json(session_id, plot_id)

        if fig_json:
            fig = pio.from_json(fig_json)
            # Cache to memory
            plot_store._plots[(session_id, plot_id)] = fig
            logger.info(f"Loaded plot {plot_id} from disk, cached to memory (session: {session_id})")
            return fig, 'disk'
    except Exception as e:
        logger.error(f"Failed to load plot {plot_id} from disk: {e}")

    return None, None

# ============================================================
# Router Setup
# ============================================================

router = APIRouter(
    prefix="/plot",
    tags=["plots"],
    responses={404: {"description": "Not found"}},
)

# ============================================================
# Service Initialization
# ============================================================

# Initialize services
plot_store = get_plot_store()
event_service = EventService()  # No database needed - uses SessionStore
# Screenshots are stored in session folders (session-aware service)
screenshot_service = ScreenshotService()  # Automatically uses current session's screenshots/ folder

# ============================================================
# API Routes
# ============================================================

@router.post("/api/create")
async def create_plot(request: Request):
    """
    Create or update a plot and return its session-scoped ID.

    Request body:
        {
            "fig_json": "...",  # Output from fig.to_json()
            "session_id": "...",  # Session identifier
            "plot_id": int  # Optional: if provided, overwrites existing plot
        }

    Returns:
        {
            "plot_id": int,  # Session-scoped ID
            "session_id": str,
            "url": "/plot/{session_id}/{plot_id}",
            "updated": bool  # True if existing plot was updated
        }
    """
    try:
        data = await request.json()
        fig_json = data.get('fig_json')
        session_id = data.get('session_id')
        plot_id = data.get('plot_id')  # Optional: for overwriting

        if not fig_json:
            return JSONResponse(
                {'error': 'Missing fig_json parameter'},
                status_code=400
            )

        if not session_id:
            return JSONResponse(
                {'error': 'Missing session_id parameter'},
                status_code=400
            )

        # Add or update plot in store (session-scoped)
        is_update = plot_id is not None
        result_plot_id, _ = plot_store.add_plot(session_id, fig_json, plot_id=plot_id)

        return {
            'plot_id': result_plot_id,
            'session_id': session_id,
            'url': f'/plot/{session_id}/{result_plot_id}',
            'updated': is_update
        }

    except Exception as e:
        return JSONResponse(
            {
                'error': str(e),
                'message': 'Failed to parse plot JSON'
            },
            status_code=400
        )


@router.post("/api/log")
async def log_event(request: Request):
    """Log interaction event and optionally save screenshot.

    Flow:
    1. INSERT event into database (get interaction_id)
    2. Save screenshot using interaction_id as filename
    3. UPDATE event with screenshot_path
    """
    try:
        data = await request.json()

        session_id = data.get('session_id')
        plot_id = data.get('plot_id')
        event_type = data.get('event_type')
        payload = data.get('payload', {})
        screenshot_data = data.get('screenshot')

        if not session_id:
            return JSONResponse(
                {'ok': False, 'error': 'Missing session_id'},
                status_code=400
            )

        # Step 1: Log to database first (get the interaction_id)
        interaction_id = event_service.log_event(
            session_id=session_id,
            plot_id=plot_id,
            event_type=event_type,
            payload=payload,
        )

        screenshot_path = None
        screenshot_size_kb = None

        # Step 2: Save screenshot using interaction_id as filename
        if screenshot_data and screenshot_data.startswith('data:image/png;base64,'):
            try:
                screenshot_path, screenshot_size_kb = screenshot_service.save_screenshot(
                    session_id=session_id,
                    plot_id=plot_id,
                    interaction_id=interaction_id,
                    screenshot_data=screenshot_data,
                )
                # Step 3: Update database with screenshot path
                event_service.update_screenshot(
                    session_id=session_id,
                    plot_id=plot_id,
                    interaction_id=interaction_id,
                    screenshot_path=screenshot_path,
                    screenshot_size_kb=screenshot_size_kb
                )
            except ValueError as e:
                logger.warning(f"Screenshot error: {e}")
            except Exception as e:
                logger.error(f"Failed to save screenshot: {e}")

        # Format and log message
        log_message = event_service.format_log_message(
            interaction_id, plot_id, event_type, screenshot_path, screenshot_size_kb
        )
        logger.info(log_message)

        return {'ok': True, 'interaction_id': interaction_id}

    except Exception as e:
        logger.error(f"Error in log_event endpoint: {e}")
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)


@router.get("/api/logs", response_class=HTMLResponse)
async def view_logs():
    """View captured interactions for all plots"""
    from .templates import render_template

    # Get events and statistics
    rows = event_service.get_events(limit=100)
    stats = event_service.get_statistics()

    # Prepare event data for template
    events = []
    for row in rows:
        id_, plot_id, timestamp, event_type, screenshot_path, size_kb = row

        # Format timestamp for display
        ts_display = timestamp[11:19] if len(timestamp) > 19 else timestamp

        # Screenshot path is stored in DB but not served via URL
        # (screenshots are captured for logging purposes, not display)

        events.append({
            'id': id_,
            'plot_id': plot_id,
            'event_type': event_type,
            'timestamp_display': ts_display,
            'has_screenshot': screenshot_path is not None,
            'size_kb': size_kb
        })

    # Render template
    html = render_template('logs.html', events=events, stats=stats)
    return HTMLResponse(content=html)


@router.get("/api/json/{session_id}/{plot_id}")
async def get_plot_json(session_id: str, plot_id: int):
    """
    Get plot JSON data for direct rendering in React.

    Returns the full plot JSON (data, layout, frames, config) plus
    view_state for restoring previous view state.
    Used by react-plotly.js for direct embedding (PlotPanel).
    """
    import json
    from ...core.session_registry import get_session_store

    fig, _ = _load_plot_figure(session_id, plot_id)

    if fig is None:
        return JSONResponse(
            {'error': f'Plot {plot_id} not found in session {session_id}'},
            status_code=404
        )

    fig_dict = json.loads(fig.to_json())

    # Get view state for state restoration on resume
    view_state = None
    try:
        session_store = get_session_store(get_logs_root())
        view_state = session_store.get_plot_view_state(session_id, plot_id)
    except Exception as e:
        logger.warning(f"Failed to get view state for plot {plot_id}: {e}")

    return {
        **fig_dict,
        'plot_id': plot_id,
        'session_id': session_id,
        'view_state': view_state
    }


@router.get("/api/view/{session_id}/{plot_id}")
async def view_plot_api(session_id: str, plot_id: int, return_data: bool = False):
    """
    View a plot: load into memory, open panel, optionally return data.

    This is the unified "view plot" operation used by:
    - Agent's get_plot_json() (return_data=True)
    - PlotHistoryDropdown (return_data=False)

    Steps:
    1. Load plot (memory → disk fallback)
    2. Cache to memory (if loaded from disk)
    3. Emit plot_show event (opens panel in UI)
    4. Return data if requested

    Args:
        session_id: Session identifier
        plot_id: Plot identifier
        return_data: If True, return plot JSON; if False, return minimal response
    """
    import json

    # 1. Load plot (caches to memory if from disk)
    fig, _ = _load_plot_figure(session_id, plot_id)

    if fig is None:
        return JSONResponse(
            {'error': f'Plot {plot_id} not found in session {session_id}'},
            status_code=404
        )

    # 2. Emit plot_show event (opens panel)
    plot_url = f"/plot/{session_id}/{plot_id}"
    try:
        await get_event_bus().publish('plot_show', {
            'plot_id': plot_id,
            'session_id': session_id,
            'url': plot_url,
            'plot_type': 'plot'
        })
        logger.debug(f"Emitted plot_show event for plot {plot_id}")
    except Exception as e:
        logger.warning(f"Failed to emit plot_show event: {e}")

    # 3. Return response
    if return_data:
        fig_dict = json.loads(fig.to_json())
        return {
            **fig_dict,
            'plot_id': plot_id,
            'session_id': session_id
        }
    else:
        return {
            'plot_id': plot_id,
            'session_id': session_id
        }


