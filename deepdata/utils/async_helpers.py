"""
Async utility functions for running synchronous code in thread pools.

Provides helpers to run blocking I/O operations without blocking the event loop.
"""

import asyncio
from typing import TypeVar, Callable, ParamSpec

P = ParamSpec('P')
T = TypeVar('T')


async def run_sync_in_thread(func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """
    Run a synchronous function in a thread pool without blocking the event loop.

    This is useful for running blocking I/O operations (like requests.get())
    in an async context without blocking the event loop.

    Args:
        func: Synchronous function to run
        *args: Positional arguments to pass to func
        **kwargs: Keyword arguments to pass to func

    Returns:
        Return value from func

    Raises:
        Any exception raised by func is propagated to caller

    Example:
        async def my_async_function():
            # Run blocking requests.get() in thread pool
            result = await run_sync_in_thread(
                requests.get,
                'http://example.com',
                timeout=5
            )
            return result
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
