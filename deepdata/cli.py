"""
Command-line interface for Deep Data.

Usage:
    deepdata                # Start web UI server
    deepdata --port 8080    # Custom port
    deepdata --help         # Show help
"""

import sys


def main():
    """Main CLI entry point."""
    # Handle --version before importing heavy modules
    if len(sys.argv) > 1 and sys.argv[1] in ['--version', '-V']:
        from . import __version__
        print(f"deepdata {__version__}")
        return

    # Default action: start the server
    # All args are passed directly to run_server
    from .web.run_server import main as run_server_main
    run_server_main()


if __name__ == "__main__":
    main()
