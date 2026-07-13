"""Debug session tracing (NDJSON). Remove after stability verification."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_DEBUG_LOG = Path(__file__).resolve().parents[1] / "debug-231386.log"
_SESSION_ID = "231386"


def debug_log(
    location: str,
    message: str,
    *,
    data: dict[str, Any] | None = None,
    hypothesis_id: str = "",
    run_id: str = "stability",
) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": _SESSION_ID,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion
