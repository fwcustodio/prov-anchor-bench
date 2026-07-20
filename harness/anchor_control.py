"""Control mechanism: append to a local log with fsync.

The measured latency includes durable local persistence — the baseline every
remote mechanism is compared against.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .config import RUNS_DIR
from .measure import now_ms
from .prov import ChainedArtifact


@dataclass(frozen=True)
class ControlResult:
    latency_ms: float
    offset: int


class ControlAnchor:
    def __init__(self, run_label: str) -> None:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self._log_path = RUNS_DIR / f"control-log-{run_label}.jsonl"
        self._offset = 0

    def anchor(self, link: ChainedArtifact) -> ControlResult:
        line = (
            json.dumps(
                {
                    "artifact": link.artifact_sha256,
                    "record": link.record_sha256,
                    "prev": link.prev_artifact_sha256,
                },
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf8")
        t0 = now_ms()
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0)
        fd = os.open(self._log_path, flags, 0o644)
        try:
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
        t1 = now_ms()
        self._offset += len(line)
        return ControlResult(latency_ms=t1 - t0, offset=self._offset)
