"""Main orchestrator for the HR Outreach Agent.

Reads top-to-bottom as plain English. All complexity is delegated
to brain.py, memory.py, and the tools/ package.

Four phases run in order each weekday morning:
    Phase 1 — Final follow-up   (day 14 contacts)
    Phase 2 — First follow-up   (day 5-7 contacts)
    Phase 3 — Fresh outreach    (new contacts in batch_size)
    Phase 4 — Reflection        (analyze stats, save settings)
"""

from __future__ import annotations

import logging
import random
import sys
import time
from datetime import datetime

# Ensure stdout/stderr can carry Unicode (Windows console defaults to
# cp1252 and would crash on the banner + emoji output).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import config
from agent.brain import OutreachBrain
from agent.memory import AgentMemory
from agent.tools import email_tool, tracker_tool


FOLLOWUP_2_MAX_PER_RUN = 3
FOLLOWUP_1_MAX_PER_RUN = 5
FOLLOWUP_SLEEP_MIN_SECONDS = 30
FOLLOWUP_SLEEP_MAX_SECONDS = 60


# ───────────────────────────────────────────────────────────────────
# Logging setup
# ───────────────────────────────────────────────────────────────────

def _configure_logging() -> None:
    logging.basicConfig(
        filename="agent.log",
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


# ───────────────────────────────────────────────────────────────────
# Pretty-print helpers (console only — never logging)
# ───────────────────────────────────────────────────────────────────

def _banner() -> None:
    today = datetime.now().strftime("%A %B %d, %Y")
    line = "═" * 58
    print(f"╔{line}╗")
    print(f"║{('HR OUTREACH AGENT — ' + today).center(58)}║")
    print(f"╚{line}╝")
    print()


def _phase_header(title: str) -> None:
    print(f"\n━━ {title} ━━━━━"
          f"━━━━━━━━━"
          f"━━━━━━━━━"
          f"━━━━━")


def _closing(next_run: str = "tomorrow 9:00 AM IST") -> None:
    print(f"\n✅ Agent cycle complete. Next run: {next_run}.")
    print("═" * 60)


# ───────────────────────────────────────────────────────────────────
# Helper: get configured batch size for today
# ───────────────────────────────────────────────────────────────────

def _resolve_batch_size(memory: AgentMemory) -> int:
    """Pull yesterday's recommended batch size from agent_settings.
    Falls back to BATCH_SIZE_DEFAULT for the first run.
    """
    settings = memory.load_agent_settings()
    if not settings:
        print(
            f"\U0001f4cb Agent self-configured: batch size = "
            f"{config.BATCH_SIZE_DEFAULT} (first run)"
        )
        return config.BATCH_SIZE_DEFAULT
    batch = settings.get("recommended_batch_size",
                         config.BATCH_SIZE_DEFAULT)
    batch = max(config.BATCH_SIZE_MIN,
                min(config.BATCH_SIZE_MAX, int(batch)))
    print(
        f"\U0001f4cb Agent self-configured: batch size = {batch}"
    )
    print("   (based on yesterday's performance)")
    return batch


# ───────────────────────────────────────────────────────────────────
# Phase 1 — Final follow-up
# ───────────────────────────────────────────────────────────────────

def phase_final_followup(brain: OutreachBrain, memory: AgentMemory) -> None:
    _phase_header("PHASE 1: FOLLOW-UP 2")
    print("\U0001f504 Checking contacts due for final follow-up...")
    due = memory.get_followup_due(2)
    print(f"   Found {len(due)} contacts.")
    if not due:
        return

    for contact in due[:FOLLOWUP_2_MAX_PER_RUN]:
        days = _days_since(contact.get("followup_1_at")) or 14
        try:
            decision = brain.decide_followup(
                contact=contact,
                days_since_sent=days,
                followup_number=2,
                original_subject=contact.get("email_subject", ""),
                original_body=contact.get("email_body", ""),
            )
        except Exception as exc:
            logging.exception("Follow-up 2 decision failed")
            memory.mark_failed(contact["id"], f"decide_followup error: {exc}")
            continue

        action = decision.get("action")
        company = contact.get("company") or "their company"
        name = contact.get("name") or "—"
        if action == "stop":
            memory.mark_stopped(contact["id"])
            print(f"   → {name} @ {company} | Day {days} | "
                  f"Stopped ({decision.get('reason', '')})")
            continue
        if action not in ("final_followup", "followup"):
            memory.mark_stopped(contact["id"])
            print(f"   → {name} @ {company} | Day {days} | "
                  f"Stopped (unknown action: {action})")
            continue

        try:
            email_tool.send_email(
                to_email=contact["email"],
                to_name=name,
                subject=decision["subject"],
                body=decision["body"],
            )
            memory.mark_followup(contact["id"], 2)
            print(f"   → {name} @ {company} | Day {days} | "
                  f"Final follow-up sent ✓")
        except email_tool.BounceError as exc:
            memory.mark_bounced(contact["id"], str(exc))
            print(f"   → {name} @ {company} | Day {days} | Bounced")
        except Exception as exc:
            logging.exception("Final follow-up send failed")
            memory.mark_failed(contact["id"], str(exc))
            print(f"   → {name} @ {company} | Day {days} | Error")

        time.sleep(random.randint(FOLLOWUP_SLEEP_MIN_SECONDS,
                                  FOLLOWUP_SLEEP_MAX_SECONDS))


# ───────────────────────────────────────────────────────────────────
# Phase 2 — First follow-up
# ───────────────────────────────────────────────────────────────────

def phase_first_followup(brain: OutreachBrain, memory: AgentMemory) -> None:
    _phase_header("PHASE 2: FOLLOW-UP 1")
    print("\U0001f504 Checking contacts due for first follow-up...")
    due = memory.get_followup_due(1)
    print(f"   Found {len(due)} contacts.")
    if not due:
        return

    for contact in due[:FOLLOWUP_1_MAX_PER_RUN]:
        days = _days_since(contact.get("sent_at")) or 5
        try:
            decision = brain.decide_followup(
                contact=contact,
                days_since_sent=days,
                followup_number=1,
                original_subject=contact.get("email_subject", ""),
                original_body=contact.get("email_body", ""),
            )
        except Exception as exc:
            logging.exception("Follow-up 1 decision failed")
            memory.mark_failed(contact["id"], f"decide_followup error: {exc}")
            continue

        action = decision.get("action")
        company = contact.get("company") or "their company"
        name = contact.get("name") or "—"
        if action == "stop":
            memory.mark_stopped(contact["id"])
            print(f"   → {name} @ {company} | Day {days} | Stopped")
            continue
        if action not in ("followup", "final_followup"):
            memory.mark_stopped(contact["id"])
            print(f"   → {name} @ {company} | Day {days} | "
                  f"Stopped (unknown action: {action})")
            continue

        try:
            email_tool.send_email(
                to_email=contact["email"],
                to_name=name,
                subject=decision["subject"],
                body=decision["body"],
            )
            memory.mark_followup(contact["id"], 1)
            print(f"   → {name} @ {company} | Day {days} | "
                  f"Follow-up sent ✓")
        except email_tool.BounceError as exc:
            memory.mark_bounced(contact["id"], str(exc))
            print(f"   → {name} @ {company} | Day {days} | Bounced")
        except Exception as exc:
            logging.exception("First follow-up send failed")
            memory.mark_failed(contact["id"], str(exc))
            print(f"   → {name} @ {company} | Day {days} | Error")

        time.sleep(random.randint(FOLLOWUP_SLEEP_MIN_SECONDS,
                                  FOLLOWUP_SLEEP_MAX_SECONDS))


# ───────────────────────────────────────────────────────────────────
# Phase 3 — Fresh outreach
# ───────────────────────────────────────────────────────────────────

def phase_fresh_outreach(
    brain: OutreachBrain,
    memory: AgentMemory,
    batch_size: int,
) -> None:
    _phase_header("PHASE 3: FRESH OUTREACH")

    if datetime.now().weekday() >= 5:
        print("Weekend detected. Skipping fresh outreach.")
        return

    contacts = memory.get_pending_contacts(batch_size)
    print(f"\U0001f4e4 Processing {len(contacts)} new contacts...\n")
    if not contacts:
        return

    sent_count = 0
    for idx, contact in enumerate(contacts, start=1):
        if sent_count >= config.DAILY_SEND_LIMIT:
            print(
                f"\n⚠️  Daily send limit "
                f"({config.DAILY_SEND_LIMIT}) reached. "
                f"Stopping to protect sender reputation."
            )
            logging.info("Daily send limit reached; stopping Phase 3.")
            break

        name = contact.get("name") or "—"
        title = contact.get("title") or "—"
        company = contact.get("company") or "—"
        print(f"[{idx}/{len(contacts)}] {name} | {title} | {company}")

        # Step a: decide
        try:
            strategy = brain.decide_strategy(contact)
        except Exception as exc:
            logging.exception("decide_strategy threw")
            memory.mark_failed(contact["id"], str(exc))
            print(f"   ❌ Strategy error — marked failed")
            continue

        # Step b: skip if brain says so
        if not strategy.get("should_send", True):
            reason = strategy.get("skip_reason") or "no reason given"
            try:
                memory.mark_skipped(contact["id"], reason)
            except Exception:
                logging.exception("mark_skipped failed")
            print(f"   ⏭️  Skipped — {reason}")
            continue

        prob = strategy.get("response_probability", 50)
        print(
            f"   \U0001f3af Angle: {strategy.get('angle', '')} | "
            f"Tone: {strategy.get('tone', '')} | Prob: {prob}%"
        )

        # Step d: write
        try:
            email = brain.write_email(contact, strategy)
        except Exception as exc:
            logging.exception("write_email failed")
            memory.mark_failed(contact["id"], f"write_email error: {exc}")
            print(f"   ❌ Email write error — marked failed")
            continue

        print(f"   ✉️  Subject: \"{email['subject']}\"")

        # Step f-h: send
        try:
            provider = email_tool.send_email(
                to_email=contact["email"],
                to_name=name,
                subject=email["subject"],
                body=email["body"],
            )
            memory.mark_sent(
                contact_id=contact["id"],
                subject=email["subject"],
                body=email["body"],
                probability=int(prob),
                sent_via=provider,
            )
            sent_count += 1
            delay = random.randint(config.DELAY_MIN_SECONDS,
                                   config.DELAY_MAX_SECONDS)
            print(f"   ✅ Sent via {provider} | Waiting {delay}s...")
            time.sleep(delay)
        except email_tool.BounceError as exc:
            memory.mark_bounced(contact["id"], str(exc))
            print(f"   ⚠️  Bounced — {exc}")
            continue
        except Exception as exc:
            # Gmail auth errors are fatal — re-raise.
            msg = str(exc)
            if "Gmail authentication failed" in msg:
                print(f"\n❌ {msg}")
                raise
            logging.exception("Send failed for contact")
            memory.mark_failed(contact["id"], msg)
            print(f"   ❌ Send error — marked failed ({msg})")
            continue


# ───────────────────────────────────────────────────────────────────
# Phase 4 — Reflection
# ───────────────────────────────────────────────────────────────────

def phase_reflection(brain: OutreachBrain, memory: AgentMemory) -> None:
    _phase_header("PHASE 4: REFLECTION")

    try:
        stats = memory.get_daily_stats()
    except Exception:
        logging.exception("get_daily_stats failed")
        print("Could not load daily stats — skipping reflection.")
        return

    print("\U0001f4ca Today's Summary:")
    print(f"   Fresh emails sent  : {stats['sent']}")
    print(f"   Follow-ups sent    : {stats['followups_sent']}")
    print(f"   Skipped            : {stats['skipped']}")
    print(f"   Failed             : {stats['failed']}")
    print(f"   Pending remaining  : {stats['total_pending_remaining']}")

    try:
        reflection = brain.analyze_performance(stats)
    except Exception:
        logging.exception("analyze_performance failed")
        reflection = {
            "tone_adjustment": "",
            "prioritize_titles": [],
            "recommended_batch_size": config.BATCH_SIZE_DEFAULT,
            "insights": "Reflection failed — keeping previous settings.",
        }

    insights = reflection.get("insights", "")
    batch = int(reflection.get("recommended_batch_size",
                               config.BATCH_SIZE_DEFAULT))

    print(f"\n\U0001f9e0 Agent Insight: {insights}")
    print(f"   Recommended batch size for tomorrow: {batch}")

    try:
        memory.save_agent_settings(reflection)
        memory.save_run_log(
            sent=stats["sent"],
            followups=stats["followups_sent"],
            skipped=stats["skipped"],
            failed=stats["failed"],
            insights=insights,
            batch=batch,
        )
    except Exception:
        logging.exception("Saving reflection results failed")

    try:
        tracker_tool.log_run(stats, insights)
    except Exception:
        logging.exception("tracker_tool.log_run failed")


# ───────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────

def _days_since(iso_string: str | None) -> int | None:
    """Return whole days between an ISO timestamp and now, or None."""
    if not iso_string:
        return None
    try:
        ts = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.now()
    return (now - ts).days


# ───────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────

def main() -> None:
    _configure_logging()
    _banner()

    config.validate()

    brain = OutreachBrain()
    memory = AgentMemory()

    batch_size = _resolve_batch_size(memory)

    phase_final_followup(brain, memory)
    phase_first_followup(brain, memory)
    phase_fresh_outreach(brain, memory, batch_size)
    phase_reflection(brain, memory)

    _closing()


if __name__ == "__main__":
    main()
