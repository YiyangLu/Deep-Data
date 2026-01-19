"""
Display helpers for terminal output.

Provides functions for displaying agent queries and responses.
"""

from rich.console import Console
from rich.markdown import Markdown


# Shared console instance to avoid repeated instantiation
_console = Console()


def display_query(prompt: str, display: bool = True) -> str:
    """Display user query in formatted style

    Args:
        prompt: User query text
        display: Whether to print to console

    Returns:
        The query text
    """
    if display:
        _console.print(f"[bold cyan]> {prompt}[/bold cyan]")
        print()  # Blank line after query
    return prompt


def display_response(text: str):
    """Display agent response as formatted markdown

    Args:
        text: Response text (markdown formatted)
    """
    if text:
        md = Markdown(text)
        _console.print(md)
        print()  # Blank line after response

def display_text_block(block, display: bool = True) -> str:
    """Display and return text from TextBlock

    Args:
        block: TextBlock from AssistantMessage
        display: Whether to print to console

    Returns:
        The text string
    """
    text = block.text
    if display and text:
        md = Markdown(text)
        _console.print(md)
        print()  # Blank line after response
    return text


def display_tool_block(block, display: bool = True) -> str:
    """Display and return formatted string from ToolUseBlock

    Args:
        block: ToolUseBlock from AssistantMessage
        display: Whether to print to console

    Returns:
        Formatted tool call string (complete input for transcript)
    """
    tool_name = block.name
    tool_input = block.input

    # For console display: show simple format with first parameter
    if display:
        # Get first parameter value for simple display
        first_param = next(iter(tool_input.values())) if tool_input else ""
        console_format = f"● {tool_name}({first_param})"

        _console.print(console_format)
        print()  # Blank line after tool call

    # For transcript: format complete input with smart line breaking
    # Try single-line format first
    formatted_params = []
    for key, value in tool_input.items():
        formatted_params.append(f"{key}={repr(value)}")

    single_line = ", ".join(formatted_params)
    max_line_length = 160

    # If fits on one line, use single-line format
    if len(single_line) <= max_line_length:
        transcript_format = f"● {tool_name}({single_line})"
    else:
        # Use multi-line format with indentation
        multi_line_params = []
        for key, value in tool_input.items():
            multi_line_params.append(f"    {key}={repr(value)}")
        params_str = ",\n".join(multi_line_params)
        transcript_format = f"● {tool_name}(\n{params_str}\n)"

    return transcript_format

def display_tool_result_block(block, display: bool = True) -> str:
    """Display and return formatted string from ToolResultBlock

    Args:
        block: ToolResultBlock from UserMessage
        display: Whether to print to console

    Returns:
        Formatted tool result string
    """
    content = block.content
    is_error = block.is_error

    # Handle content as list or string
    if isinstance(content, list):
        # Convert list to string representation
        content = str(content)

    # Split content into lines and indent continuation lines for transcript
    lines = content.split('\n')
    if len(lines) > 1:
        # First line with marker, rest indented to align
        indented_lines = [lines[0]]
        for line in lines[1:]:
            indented_lines.append('     ' + line)  # 5 spaces to align with content after ⎿
        content_formatted = '\n'.join(indented_lines)
    else:
        content_formatted = content

    # Format based on error status
    if is_error:
        formatted = f"  ⎿ [ERROR] {content_formatted}"
    else:
        formatted = f"  ⎿ {content_formatted}"

    if display:
        if is_error:
            _console.print(f"[red]{formatted}[/red]")
        else:
            _console.print(formatted)
        print()  # Blank line after result

    return formatted


def render_markdown(text: str):
    """Render markdown text to terminal (alias for display_response)

    Args:
        text: Markdown-formatted text
    """
    md = Markdown(text)
    _console.print(md)
