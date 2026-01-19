"""
Session storage module.

Refactored from monolithic session_store.py into separate modules:
- info.py: SessionInfo dataclass
- queries.py: Query methods mixin
- export.py: Export and deletion mixin
- store.py: Main SessionStore class
"""

from .info import SessionInfo
from .store import SessionStore

__all__ = ['SessionStore', 'SessionInfo']
