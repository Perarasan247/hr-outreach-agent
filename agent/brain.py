"""Gemini-powered reasoning engine for the HR Outreach Agent.

The brain owns all LLM calls. It exposes four high-level methods
used by agent.py:

    decide_strategy(contact)               -> dict
    write_email(contact, strategy)         -> dict
    decide_followup(contact, days_since,
                    followup_number, original)
                                           -> dict
    analyze_performance(stats)             -> dict

Plus a private spam-filter pass (filter_spam_content) that runs
on every Gemini-generated subject/hook/CTA before assembly.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

import google.generativeai as genai

import config
from agent.tools.email_tool import _build_email_body
from prompts.decision_prompt import DECISION_PROMPT
from prompts.email_writer_prompt import EMAIL_WRITER_PROMPT
from prompts.followup_prompt import FOLLOWUP_PROMPT
from prompts.reflection_prompt import REFLECTION_PROMPT


SPAM_TRIGGERS = [
    "free", "guaranteed", "urgent", "act now", "winner",
    "exclusive offer", "click here", "earn money",
    "make money", "opportunity", "apply now", "immediate",
    "great offer", "special promotion", "no obligation",
    "limited time", "unsubscribe", "risk-free", "bonus",
    "cash", "cheap", "miracle", "incredible deal",
    "no cost", "only $", "save big", "subscribe",
    "take action now", "you have been selected",
    "congratulations", "dear friend", "this is not spam",
]


class OutreachBrain:
    """Wraps Gemini for decisions and email generation."""

    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self) -> None:
        genai.configure(api_key=config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(self.MODEL_NAME)
        self._decision_cfg = genai.types.GenerationConfig(temperature=0.3)
        self._writer_cfg = genai.types.GenerationConfig(temperature=0.8)

    # ───────────────────────────────────────────────────────
    # Public methods
    # ───────────────────────────────────────────────────────

    def decide_strategy(self, contact: dict) -> dict:
        """Decide whether to email this contact and how.

        Returns a dict with keys: should_send, send_reason, tone,
        angle, red_flags, response_probability, skip_reason.
        On any failure, returns a sensible default that proceeds
        with the email.
        """
        prompt = DECISION_PROMPT.format(
            my_name=config.MY_NAME,
            target_role=config.MY_TARGET_ROLE,
            name=contact.get("name", ""),
            title=contact.get("title", ""),
            company=contact.get("company", ""),
            email=contact.get("email", ""),
            today=date.today().isoformat(),
        )
        try:
            resp = self.model.generate_content(
                prompt, generation_config=self._decision_cfg
            )
            parsed = self._parse_json(resp.text)
        except Exception as exc:
            logging.error(f"decide_strategy Gemini call failed: {exc}")
            return self._default_strategy()

        # Coerce types defensively.
        parsed.setdefault("should_send", True)
        parsed.setdefault("send_reason", "")
        parsed.setdefault("tone", "conversational")
        parsed.setdefault("angle", "job-opportunity")
        parsed.setdefault("red_flags", [])
        parsed.setdefault("response_probability", 50)
        parsed.setdefault("skip_reason", "")
        try:
            parsed["response_probability"] = int(parsed["response_probability"])
        except (TypeError, ValueError):
            parsed["response_probability"] = 50
        return parsed

    def write_email(self, contact: dict, strategy: dict) -> dict:
        """Generate the opening hook + CTA, filter for spam, and
        assemble the final email body.

        Returns dict with keys: subject, body, opening_hook, cta.
        On parse failure: retries once, then raises ValueError.
        """
        prompt = EMAIL_WRITER_PROMPT.format(
            my_name=config.MY_NAME,
            my_target_role=config.MY_TARGET_ROLE,
            my_experience_years=config.MY_EXPERIENCE_YEARS,
            my_key_skill_1=config.MY_KEY_SKILL_1,
            my_key_skill_2=config.MY_KEY_SKILL_2,
            my_key_skill_3=config.MY_KEY_SKILL_3,
            my_current_project=config.MY_CURRENT_PROJECT,
            name=contact.get("name", ""),
            title=contact.get("title", ""),
            company=contact.get("company", ""),
            tone=strategy.get("tone", "conversational"),
            angle=strategy.get("angle", "job-opportunity"),
        )

        parsed = self._generate_email_json(prompt, retries=1)
        subject = parsed.get("subject", "").strip()
        opening_hook = parsed.get("opening_hook", "").strip()
        cta = parsed.get("cta", "").strip()

        cleaned = self.filter_spam_content(subject, opening_hook, cta)
        body = _build_email_body(
            name=contact.get("name", ""),
            company=contact.get("company", ""),
            opening_hook=cleaned["opening_hook"],
            cta=cleaned["cta"],
        )
        return {
            "subject": cleaned["subject"],
            "body": body,
            "opening_hook": cleaned["opening_hook"],
            "cta": cleaned["cta"],
        }

    def decide_followup(
        self,
        contact: dict,
        days_since_sent: int,
        followup_number: int,
        original_subject: str = "",
        original_body: str = "",
    ) -> dict:
        """Decide whether to follow up and produce the email if so.

        Returns dict with keys: action, reason, subject, body.
        action is one of "followup", "final_followup", "stop".
        When action == "stop", subject and body are empty strings.
        """
        # Hard rule: never a 3rd follow-up.
        if followup_number > config.MAX_FOLLOWUPS:
            return {
                "action": "stop",
                "reason": "Max follow-ups reached",
                "subject": "",
                "body": "",
            }

        prompt = FOLLOWUP_PROMPT.format(
            days_since_sent=days_since_sent,
            original_subject=original_subject,
            original_body=original_body,
            name=contact.get("name", ""),
            title=contact.get("title", ""),
            company=contact.get("company", ""),
            followup_number=followup_number,
        )

        try:
            resp = self.model.generate_content(
                prompt, generation_config=self._writer_cfg
            )
            parsed = self._parse_json(resp.text)
        except Exception as exc:
            logging.error(f"decide_followup Gemini call failed: {exc}")
            return {
                "action": "stop",
                "reason": f"LLM error: {exc}",
                "subject": "",
                "body": "",
            }

        action = parsed.get("action", "stop")
        reason = parsed.get("reason", "")

        if action == "stop":
            return {"action": "stop", "reason": reason,
                    "subject": "", "body": ""}

        subject = parsed.get("subject", "").strip()
        opening_hook = parsed.get("opening_hook", "").strip()
        cta = parsed.get("cta", "").strip()

        cleaned = self.filter_spam_content(subject, opening_hook, cta)
        body = _build_email_body(
            name=contact.get("name", ""),
            company=contact.get("company", ""),
            opening_hook=cleaned["opening_hook"],
            cta=cleaned["cta"],
        )
        return {
            "action": action,
            "reason": reason,
            "subject": cleaned["subject"],
            "body": body,
        }

    def analyze_performance(self, stats: dict) -> dict:
        """Reflect on the day's stats and recommend tomorrow's plan.

        Returns dict with keys: tone_adjustment, prioritize_titles,
        recommended_batch_size, insights.
        On failure, returns a sensible default that keeps the
        previous batch size.
        """
        prompt = REFLECTION_PROMPT.format(
            sent=stats.get("sent", 0),
            followups_sent=stats.get("followups_sent", 0),
            skipped=stats.get("skipped", 0),
            failed=stats.get("failed", 0),
            bounced=stats.get("bounced", 0),
            pending_remaining=stats.get("total_pending_remaining", 0),
        )

        try:
            resp = self.model.generate_content(
                prompt, generation_config=self._decision_cfg
            )
            parsed = self._parse_json(resp.text)
        except Exception as exc:
            logging.error(f"analyze_performance Gemini call failed: {exc}")
            return {
                "tone_adjustment": "Keep conversational tone",
                "prioritize_titles": [],
                "recommended_batch_size": config.BATCH_SIZE_DEFAULT,
                "insights": f"Reflection skipped: {exc}",
            }

        # Clamp recommended batch size into the allowed range.
        try:
            batch = int(parsed.get("recommended_batch_size",
                                   config.BATCH_SIZE_DEFAULT))
        except (TypeError, ValueError):
            batch = config.BATCH_SIZE_DEFAULT
        batch = max(config.BATCH_SIZE_MIN,
                    min(config.BATCH_SIZE_MAX, batch))
        parsed["recommended_batch_size"] = batch

        parsed.setdefault("tone_adjustment", "Keep conversational tone")
        parsed.setdefault("prioritize_titles", [])
        parsed.setdefault("insights", "")
        return parsed

    # ───────────────────────────────────────────────────────
    # Spam filter
    # ───────────────────────────────────────────────────────

    def filter_spam_content(
        self,
        subject: str,
        opening_hook: str,
        cta: str,
    ) -> dict:
        """Scan Gemini output for spam triggers. If any are found,
        ask Gemini to rewrite the flagged parts. Returns dict with
        keys: subject, opening_hook, cta.

        Falls back to the original content if the rewrite fails.
        """
        combined = f"{subject} {opening_hook} {cta}".lower()
        found = [t for t in SPAM_TRIGGERS if t in combined]
        if not found:
            return {
                "subject": subject,
                "opening_hook": opening_hook,
                "cta": cta,
            }

        logging.warning(
            f"Spam triggers detected: {found}. Requesting rewrite."
        )

        rewrite_prompt = (
            f"The following email content contains spam trigger words: "
            f"{found}\n\n"
            f"Original subject: {subject}\n"
            f"Original opening: {opening_hook}\n"
            f"Original CTA: {cta}\n\n"
            "Rewrite ONLY the parts that contain spam words. Keep "
            "the same meaning but use natural, conversational, "
            "professional language. No spam trigger words "
            "whatsoever.\n\n"
            "Return ONLY valid JSON:\n"
            '{\n  "subject": "...",\n  "opening_hook": "...",\n  '
            '"cta": "..."\n}'
        )

        try:
            resp = self.model.generate_content(
                rewrite_prompt, generation_config=self._writer_cfg
            )
            parsed = self._parse_json(resp.text)
            return {
                "subject": parsed.get("subject", subject),
                "opening_hook": parsed.get("opening_hook", opening_hook),
                "cta": parsed.get("cta", cta),
            }
        except Exception as exc:
            logging.warning(
                f"Spam-rewrite failed ({exc}); using original content."
            )
            return {
                "subject": subject,
                "opening_hook": opening_hook,
                "cta": cta,
            }

    # ───────────────────────────────────────────────────────
    # Private helpers
    # ───────────────────────────────────────────────────────

    def _generate_email_json(self, prompt: str, retries: int = 1) -> dict:
        """Call Gemini for an email-writing prompt and parse JSON.

        Retries once on parse/network failure. Raises ValueError
        if all attempts fail.
        """
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self.model.generate_content(
                    prompt, generation_config=self._writer_cfg
                )
                return self._parse_json(resp.text)
            except Exception as exc:
                last_exc = exc
                logging.warning(
                    f"Email JSON generation attempt "
                    f"{attempt + 1} failed: {exc}"
                )
        raise ValueError(
            f"Gemini email generation failed after "
            f"{retries + 1} attempts: {last_exc}"
        )

    def _parse_json(self, text: str) -> dict:
        """Parse JSON from a Gemini response, stripping markdown
        fences and surrounding whitespace. Raises on failure after
        logging the raw text.
        """
        if not text:
            raise ValueError("Empty Gemini response")
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logging.error(
                f"JSON parse failed. Raw Gemini text:\n{text}"
            )
            raise ValueError(f"Gemini did not return valid JSON: {exc}") from exc

    @staticmethod
    def _default_strategy() -> dict:
        """Sensible default when decide_strategy fails."""
        return {
            "should_send": True,
            "send_reason": "default (LLM failure)",
            "tone": "conversational",
            "angle": "job-opportunity",
            "red_flags": [],
            "response_probability": 50,
            "skip_reason": "",
        }
