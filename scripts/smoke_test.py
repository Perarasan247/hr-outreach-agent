"""One-shot smoke test — sends a real email to each pending contact
in the DB while bypassing the brain's HR-quality filter.

Purpose: verify that the full pipeline (Gemini email writing + spam
filter + Resend/Gmail send + Supabase mark_sent) works end-to-end,
without depending on whether the brain decides the contact looks
HR-y enough.

DO NOT use against the full 1842-row list. Only run it after seeding
a small set of test addresses you control.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import config  # noqa: E402
from agent.brain import OutreachBrain  # noqa: E402
from agent.memory import AgentMemory  # noqa: E402
from agent.tools import email_tool  # noqa: E402


FORCED_STRATEGY = {
    "should_send": True,
    "tone": "conversational",
    "angle": "job-opportunity",
    "response_probability": 70,
}


def main() -> None:
    config.validate()

    # Reset any contacts the previous run skipped, so this run can
    # reach them through get_pending_contacts.
    from supabase import create_client
    sb = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    sb.table("contacts").update({
        "status": "pending",
        "skip_reason": None,
        "error_message": None,
        "sent_at": None,
    }).in_("status", ["skipped", "failed"]).execute()

    brain = OutreachBrain()
    memory = AgentMemory()

    contacts = memory.get_pending_contacts(10)
    print(f"Found {len(contacts)} pending contacts to smoke-test.\n")

    sent = 0
    failed = 0
    for contact in contacts:
        name = contact.get("name") or contact["email"]
        print(f"→ {name} <{contact['email']}>")

        try:
            email = brain.write_email(contact, FORCED_STRATEGY)
        except Exception as exc:
            print(f"  Email-write failed: {exc}")
            memory.mark_failed(contact["id"], str(exc))
            failed += 1
            continue

        print(f"  Subject: {email['subject']}")

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
                probability=FORCED_STRATEGY["response_probability"],
                sent_via=provider,
            )
            sent += 1
            print(f"  Sent via {provider}\n")
        except email_tool.BounceError as exc:
            memory.mark_bounced(contact["id"], str(exc))
            failed += 1
            print(f"  Bounced: {exc}\n")
        except Exception as exc:
            memory.mark_failed(contact["id"], str(exc))
            failed += 1
            print(f"  Send error: {exc}\n")

    print(f"\nDone. Sent: {sent} | Failed: {failed}")


if __name__ == "__main__":
    main()
