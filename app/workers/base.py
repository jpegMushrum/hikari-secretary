from __future__ import annotations

from typing import Protocol


class BackgroundWorker(Protocol):
    """Long-running process managed by the application lifecycle."""

    name: str

    async def run(self) -> None: ...
