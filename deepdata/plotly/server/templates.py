"""
HTML template rendering for plotly visualizations.

Provides Jinja2 template rendering with proper configuration for
generating interactive plot viewers with event capture.
"""

import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .capture_config import CAPTURE_CONFIG, SCREENSHOT_CONFIG


# Get templates directory (same directory as this file)
TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_jinja_env() -> Environment:
    """
    Create and configure Jinja2 environment.

    Returns:
        Configured Jinja2 Environment
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True
    )
    return env


# Global Jinja2 environment instance
_jinja_env = create_jinja_env()


def render_template(template_name: str, **context) -> str:
    """
    Render a Jinja2 template with the given context.

    Args:
        template_name: Name of template file (e.g., 'plot.html')
        **context: Template variables to pass to template

    Returns:
        Rendered HTML string

    Raises:
        jinja2.TemplateNotFound: If template file doesn't exist
        jinja2.TemplateSyntaxError: If template has syntax errors

    Example:
        html = render_template('plot.html',
                              plot_id=1,
                              fig_json={'data': [...], 'layout': {...}})
    """
    template = _jinja_env.get_template(template_name)
    return template.render(**context)


def generate_plot_html(fig, plot_id: int) -> str:
    """
    Generate HTML for plot viewer with interaction capture.

    Uses Jinja2 template for clean separation of HTML and Python code.

    Args:
        fig: Plotly figure object
        plot_id: Plot identifier

    Returns:
        Rendered HTML string
    """
    fig_json = json.loads(fig.to_json())

    return render_template(
        'plot.html',
        plot_id=plot_id,
        fig_json=fig_json,
        capture_config=CAPTURE_CONFIG,
        screenshot_config=SCREENSHOT_CONFIG
    )
