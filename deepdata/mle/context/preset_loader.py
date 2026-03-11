"""Simple JSON preset loader."""

import json
from pathlib import Path

from .base import Context, resolve_context


PRESETS_DIR = Path(__file__).parent / "presets"


def load_preset(name: str) -> dict:
    """Load preset JSON."""
    path = PRESETS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Preset not found: {path}")
    with open(path) as f:
        return json.load(f)


def list_presets() -> list[str]:
    """List available preset names."""
    return [p.stem for p in PRESETS_DIR.glob("*.json")]


async def get_context(workspace: Path, preset: str = "mlebench") -> Context:
    """Load preset and create Context."""
    data = load_preset(preset)
    return resolve_context(workspace, data)
