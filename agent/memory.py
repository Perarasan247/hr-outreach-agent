"""Supabase persistence layer for the HR Outreach Agent.

All database I/O lives here. The rest of the agent never touches
the Supabase client directly. Methods are written so that one
contact's failure does not poison the rest of the run — callers
catch and continue.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timezone
from typing import Optional

from supabase import Client, create_client

import config


class AgentMemory:
    """Thin wrapper around the Supabase client.

    Initializes the client at construction time. If the client
    cannot be created (e.g. URL/key wrong), prints a clear message
    and exits — there is no point continuing without a database.
    """

    SETTINGS_KEY = "daily_config"

    def __init__(self) -> None:
        try:
            self.client: Client = create_client(
                config.SUPABASE_URL, config.SUPABASE_KEY
            )
        except Exception as exc:
            print(
                "Cannot connect to Supabase. Check SUPABASE_URL and "
                "SUPABASE_KEY."
            )
            logging.error(f"Supabase init failed: {exc}")
            sys.exit(1)

    # ─── Read queries ───────────────────────────────────────────

    def get_pending_contacts(self, limit: int) -> list[dict]:
        """Return up to `limit` contacts with status='pending',
        ordered by id ascending.
        """
        try:
            resp = (
                self.client.table("contacts")
                .select("*")
                .eq("status", "pending")
                .order("id", desc=False)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as exc:
            logging.error(f"get_pending_contacts failed: {exc}")
            raise

    def get_followup_due(self, followup_number: int) -> list[dict]:
        """Return contacts due for follow-up.

        followup_number == 1: status='sent' AND followup_count=0
            AND sent_at <= now - 5 days
        followup_number == 2: status='followup_1' AND followup_count=1
            AND followup_1_at <= now - 14 days
        """
        try:
            if followup_number == 1:
                cutoff = self._days_ago_iso(config.FOLLOWUP_1_AFTER_DAYS)
                resp = (
                    self.client.table("contacts")
                    .select("*")
                    .eq("status", "sent")
                    .eq("followup_count", 0)
                    .lte("sent_at", cutoff)
                    .order("sent_at", desc=False)
                    .execute()
                )
            elif followup_number == 2:
                cutoff = self._days_ago_iso(config.FOLLOWUP_2_AFTER_DAYS)
                resp = (
                    self.client.table("contacts")
                    .select("*")
                    .eq("status", "followup_1")
                    .eq("followup_count", 1)
                    .lte("followup_1_at", cutoff)
                    .order("followup_1_at", desc=False)
                    .execute()
                )
            else:
                return []
            return resp.data or []
        except Exception as exc:
            logging.error(f"get_followup_due({followup_number}) failed: {exc}")
            raise

    # ─── Write / update mutations ──────────────────────────────

    def mark_sent(
        self,
        contact_id: int,
        subject: str,
        body: str,
        probability: int,
        sent_via: str,
    ) -> None:
        """Mark a contact as freshly emailed (status='sent')."""
        try:
            self.client.table("contacts").update({
                "status": "sent",
                "sent_at": self._now_iso(),
                "email_subject": subject,
                "email_body": body,
                "response_probability": probability,
                "sent_via": sent_via,
            }).eq("id", contact_id).execute()
        except Exception as exc:
            logging.error(f"mark_sent({contact_id}) failed: {exc}")
            raise

    def mark_followup(self, contact_id: int, followup_number: int) -> None:
        """Update status after a follow-up has been sent."""
        try:
            if followup_number == 1:
                payload = {
                    "status": "followup_1",
                    "followup_1_at": self._now_iso(),
                    "followup_count": 1,
                }
            elif followup_number == 2:
                payload = {
                    "status": "followup_2",
                    "followup_2_at": self._now_iso(),
                    "followup_count": 2,
                }
            else:
                return
            self.client.table("contacts").update(payload).eq(
                "id", contact_id
            ).execute()
        except Exception as exc:
            logging.error(f"mark_followup({contact_id}, {followup_number}) failed: {exc}")
            raise

    def mark_stopped(self, contact_id: int) -> None:
        """Permanently stop further follow-ups for a contact."""
        try:
            self.client.table("contacts").update(
                {"status": "stopped"}
            ).eq("id", contact_id).execute()
        except Exception as exc:
            logging.error(f"mark_stopped({contact_id}) failed: {exc}")
            raise

    def mark_skipped(self, contact_id: int, reason: str) -> None:
        """Skip a contact (the brain decided not to email)."""
        try:
            self.client.table("contacts").update({
                "status": "skipped",
                "skip_reason": reason,
            }).eq("id", contact_id).execute()
        except Exception as exc:
            logging.error(f"mark_skipped({contact_id}) failed: {exc}")
            raise

    def mark_failed(self, contact_id: int, error: str) -> None:
        """Record a technical failure for a single contact."""
        try:
            self.client.table("contacts").update({
                "status": "failed",
                "error_message": error[:2000],
            }).eq("id", contact_id).execute()
        except Exception as exc:
            logging.error(f"mark_failed({contact_id}) failed: {exc}")
            raise

    def mark_bounced(self, contact_id: int, error: str) -> None:
        """Record a bounced email for a single contact."""
        try:
            self.client.table("contacts").update({
                "status": "bounced",
                "error_message": error[:2000],
            }).eq("id", contact_id).execute()
        except Exception as exc:
            logging.error(f"mark_bounced({contact_id}) failed: {exc}")
            raise

    # ─── Daily stats / settings ────────────────────────────────

    def get_daily_stats(self) -> dict:
        """Aggregate today's activity from the contacts table.

        Returns dict with keys: sent, followups_sent, skipped,
        failed, bounced, total_pending_remaining.
        """
        try:
            today_iso = date.today().isoformat()

            def _count(query):
                resp = query.execute()
                return len(resp.data or [])

            sent = _count(
                self.client.table("contacts")
                .select("id")
                .eq("status", "sent")
                .gte("sent_at", today_iso)
            )

            fu1 = _count(
                self.client.table("contacts")
                .select("id")
                .eq("status", "followup_1")
                .gte("followup_1_at", today_iso)
            )
            fu2 = _count(
                self.client.table("contacts")
                .select("id")
                .eq("status", "followup_2")
                .gte("followup_2_at", today_iso)
            )
            followups_sent = fu1 + fu2

            skipped = _count(
                self.client.table("contacts")
                .select("id")
                .eq("status", "skipped")
            )
            failed = _count(
                self.client.table("contacts")
                .select("id")
                .eq("status", "failed")
            )
            bounced = _count(
                self.client.table("contacts")
                .select("id")
                .eq("status", "bounced")
            )
            pending_remaining = _count(
                self.client.table("contacts")
                .select("id")
                .eq("status", "pending")
            )

            return {
                "sent": sent,
                "followups_sent": followups_sent,
                "skipped": skipped,
                "failed": failed,
                "bounced": bounced,
                "total_pending_remaining": pending_remaining,
            }
        except Exception as exc:
            logging.error(f"get_daily_stats failed: {exc}")
            raise

    def save_agent_settings(self, settings: dict) -> None:
        """Upsert the daily_config row in agent_settings."""
        try:
            self.client.table("agent_settings").upsert(
                {
                    "key": self.SETTINGS_KEY,
                    "value": settings,
                    "updated_at": self._now_iso(),
                },
                on_conflict="key",
            ).execute()
        except Exception as exc:
            logging.error(f"save_agent_settings failed: {exc}")
            raise

    def load_agent_settings(self) -> Optional[dict]:
        """Return the daily_config JSONB value, or None if absent."""
        try:
            resp = (
                self.client.table("agent_settings")
                .select("value")
                .eq("key", self.SETTINGS_KEY)
                .limit(1)
                .execute()
            )
            rows = resp.data or []
            if not rows:
                return None
            return rows[0].get("value")
        except Exception as exc:
            logging.error(f"load_agent_settings failed: {exc}")
            raise

    def save_run_log(
        self,
        sent: int,
        followups: int,
        skipped: int,
        failed: int,
        insights: str,
        batch: int,
    ) -> None:
        """Append one row to the run_logs table."""
        try:
            self.client.table("run_logs").insert({
                "run_date": date.today().isoformat(),
                "sent_count": sent,
                "followup_count": followups,
                "skipped_count": skipped,
                "failed_count": failed,
                "insights": insights,
                "recommended_batch": batch,
            }).execute()
        except Exception as exc:
            logging.error(f"save_run_log failed: {exc}")
            raise

    # ─── Internal helpers ──────────────────────────────────────

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _days_ago_iso(days: int) -> str:
        from datetime import timedelta
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
