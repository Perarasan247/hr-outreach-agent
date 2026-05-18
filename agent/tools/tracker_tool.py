"""Run-summary logger.

Appends a one-paragraph summary of each agent run to
`runs_history.txt` at the project root. This is human-readable
output, separate from the per-event logging done via the standard
logging module.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

_LOG_PATH = Path("runs_history.txt")


def log_run(stats: dict, insights: str) -> None:
    """Append a formatted run summary to runs_history.txt.

    Args:
        stats: Dict produced by AgentMemory.get_daily_stats().
               Expected keys: sent, followups_sent, skipped,
               failed, total_pending_remaining.
        insights: Free-form insight string from the brain's
                  analyze_performance() output.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sent = stats.get("sent", 0)
    followups = stats.get("followups_sent", 0)
    skipped = stats.get("skipped", 0)
    failed = stats.get("failed", 0)
    pending = stats.get("total_pending_remaining", 0)

    block = (
        "============================================================\n"
        f"RUN: {now}\n"
        f"Sent: {sent} | Follow-ups: {followups} | "
        f"Skipped: {skipped} | Failed: {failed}\n"
        f"Pending remaining: {pending}\n"
        f"Insight: {insights}\n"
        "============================================================\n"
    )

    with _LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(block)
