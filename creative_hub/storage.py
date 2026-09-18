from __future__ import annotations

import json
from pathlib import Path

from domain import HubState, default_state, state_from_dict, state_to_dict


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> HubState:
        if not self.path.exists():
            return default_state()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default_state()
        return state_from_dict(data if isinstance(data, dict) else {})

    def save(self, state: HubState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(state_to_dict(state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)
