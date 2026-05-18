"""Email sending tool with Resend (primary) and Gmail SMTP (fallback).

Exposes:
    send_email(to_email, to_name, subject, body) -> str
        Returns the provider name used ('resend' or 'gmail_smtp').
        Raises BounceError if the recipient is refused by both.
        Raises Exception on any other unrecoverable failure.

    _build_email_body(name, company, opening_hook, cta) -> str
        Assembles the deterministic 7-part email body from the
        Gemini-generated hook and CTA plus the sender profile in
        config.py. Called by brain.py before sending.

The Gemini layer is responsible for the hook and CTA only — all
other parts of the body are produced here so every email is
structurally identical.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
import textwrap
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config


class BounceError(Exception):
    """Raised when the recipient is refused by SMTP / Resend."""


# ───────────────────────────────────────────────────────────────────
# Subject / body cleanup helpers
# ───────────────────────────────────────────────────────────────────

_SUBJECT_FORBIDDEN_CHARS = ("!", "$", "%", "#", "*")
_REPLY_PREFIXES = ("re:", "fw:", "fwd:")


def _clean_subject(subject: str, name: str) -> str:
    """Strip spam-prone characters and prefixes from a subject line
    and enforce the 45-character limit. Returns a safe fallback if
    empty.
    """
    cleaned = (subject or "").strip()

    # Strip RE:/FW: prefixes — this is fresh outreach, not a reply.
    lower = cleaned.lower()
    for prefix in _REPLY_PREFIXES:
        while lower.startswith(prefix):
            cleaned = cleaned[len(prefix):].lstrip()
            lower = cleaned.lower()

    for ch in _SUBJECT_FORBIDDEN_CHARS:
        cleaned = cleaned.replace(ch, "")
    cleaned = cleaned.strip()

    if not cleaned:
        cleaned = f"Quick question, {_first_name(name)}"

    # If the entire subject is screaming caps, downcase it.
    if (cleaned.isupper() or
            (sum(c.isupper() for c in cleaned) >
             max(1, sum(c.isalpha() for c in cleaned)) * 0.6)):
        cleaned = cleaned.lower()

    # Title-case the first character only, leave the rest as-is.
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]

    if len(cleaned) > 60:
        cleaned = cleaned[:57].rstrip() + "..."
    return cleaned


def _clean_body_for_spam(body: str) -> str:
    """Final pass cleanup before sending.

    Strips trailing whitespace on each line and collapses any
    consecutive blank lines into a single blank line.
    """
    lines = body.split("\n")
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        line = line.rstrip()
        is_blank = len(line.strip()) == 0
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank
    return "\n".join(cleaned)


def _wrap_paragraphs(text: str, width: int = 72) -> str:
    """Normalize each paragraph in `text` into a single line and
    re-join with blank lines between paragraphs.

    Note: we no longer hard-wrap at `width`. Modern email clients
    (Gmail in particular) render pre-wrapped plain-text emails as
    narrow blocks that don't use the available reading pane. We
    keep the `width` parameter for API compatibility but ignore it.
    """
    del width  # intentionally unused — kept for backwards compat
    paragraphs = text.split("\n\n")
    cleaned = [" ".join(p.split()) for p in paragraphs if p.strip()]
    return "\n\n".join(cleaned)


def _first_name(full_name: str) -> str:
    """Return the first word of a full name, or the original string
    if it's empty/whitespace.

    Used in the greeting so "Akanksha Puri" becomes "Akanksha" and
    "Arasu Tester" becomes "Arasu" — matching cold-email convention.
    """
    parts = (full_name or "").strip().split()
    return parts[0] if parts else full_name


# ───────────────────────────────────────────────────────────────────
# Body assembly
# ───────────────────────────────────────────────────────────────────

def _build_email_body(name: str, company: str, opening_hook: str, cta: str) -> str:
    """Assemble the full 7-part email body.

    Args:
        name:          Recipient first name (used in greeting).
        company:       Recipient company (used in the ask).
        opening_hook:  Gemini-generated PART 2 — 1-2 sentences.
        cta:           Gemini-generated PART 5 — one sentence.

    Returns the assembled, line-wrapped, spam-cleaned body text.
    """
    # PART 1 — greeting (first name only)
    greeting = f"Hi {_first_name(name)},"

    # PART 2 — opening hook (wrapped)
    hook = _wrap_paragraphs(opening_hook.strip(), width=72)

    # PART 3 — who I am (verbatim from MY_INTRO env var)
    who_i_am = _wrap_paragraphs(config.MY_INTRO.strip(), width=72)

    # PART 4 — the ask (uses MY_LOOKING_FOR + {company})
    the_ask = _wrap_paragraphs(
        f"I'm actively looking for {config.MY_LOOKING_FOR} opportunities. "
        f"If you think I might be a good fit at {company}, I'd love to "
        f"hear from you.",
        width=72,
    )

    # PART 5 — soft CTA
    cta_text = _wrap_paragraphs(cta.strip(), width=72)

    # PART 6 — signature (fixed)
    signature = (
        "Warm regards,\n"
        f"{config.MY_NAME}\n\n"
        f"\U0001f4e7 Email     : {config.MY_EMAIL_DISPLAY}\n"
        f"\U0001f4f1 Phone     : {config.MY_PHONE}\n"
        f"\U0001f310 Portfolio : {config.MY_PORTFOLIO_URL}\n"
        f"\U0001f4c4 Resume    : {config.MY_RESUME_URL}\n"
        f"\U0001f517 LinkedIn  : {config.MY_LINKEDIN_URL}\n"
        f"\U0001f419 GitHub    : {config.MY_GITHUB_URL}"
    )

    # PART 7 — P.S. line (fixed)
    ps = (
        "P.S. If this isn't relevant, no worries at all — feel free "
        "to ignore this."
    )

    body = "\n\n".join([
        greeting,
        hook,
        who_i_am,
        the_ask,
        cta_text,
        signature,
        ps,
    ])

    return _clean_body_for_spam(body)


# ───────────────────────────────────────────────────────────────────
# Provider implementations
# ───────────────────────────────────────────────────────────────────

def _send_via_resend(to_email: str, to_name: str, subject: str, body: str) -> None:
    """Send via the Resend HTTP API. Raises on any error."""
    import resend

    resend.api_key = config.RESEND_API_KEY
    params = {
        "from": f"{config.MY_NAME} <{config.GMAIL_ADDRESS}>",
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    resend.Emails.send(params)


def _send_via_gmail(to_email: str, to_name: str, subject: str, body: str) -> None:
    """Send via Gmail SMTP over SSL. Raises smtplib exceptions on error."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config.MY_NAME} <{config.GMAIL_ADDRESS}>"
    msg["To"] = to_email
    msg["MIME-Version"] = "1.0"
    msg["X-Mailer"] = "Python"
    msg["Precedence"] = "normal"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        server.sendmail(config.GMAIL_ADDRESS, [to_email], msg.as_string())


# ───────────────────────────────────────────────────────────────────
# Public entry point
# ───────────────────────────────────────────────────────────────────

def send_email(to_email: str, to_name: str, subject: str, body: str) -> str:
    """Send an email via Resend first; fall back to Gmail SMTP on
    any Resend failure.

    Args:
        to_email: Recipient address.
        to_name:  Recipient display name (used in From header
                  display only when needed).
        subject:  Already-assembled subject. Will be cleaned here.
        body:     Already-assembled body. Will be cleaned here.

    Returns the provider name used: 'resend' or 'gmail_smtp'.

    Raises:
        BounceError: Recipient refused by both providers.
        Exception:   Both providers failed for technical reasons,
                     or Gmail auth failed (in which case the
                     message instructs the user to fix
                     GMAIL_APP_PASSWORD).
    """
    safe_subject = _clean_subject(subject, to_name or to_email)
    safe_body = _clean_body_for_spam(body)

    resend_error_message: str | None = None

    # ── Try Resend first ──
    try:
        _send_via_resend(to_email, to_name, safe_subject, safe_body)
        logging.info(f"Sent via Resend to {to_email}")
        return "resend"
    except Exception as resend_error:
        resend_error_message = str(resend_error)
        logging.warning(
            f"Resend failed for {to_email}: {resend_error}. "
            f"Falling back to Gmail SMTP..."
        )

    # ── Fallback to Gmail SMTP ──
    try:
        _send_via_gmail(to_email, to_name, safe_subject, safe_body)
        logging.info(f"Sent via Gmail SMTP (fallback) to {to_email}")
        return "gmail_smtp"
    except smtplib.SMTPRecipientsRefused as exc:
        raise BounceError(
            f"Recipient refused by both providers: {to_email} ({exc})"
        ) from exc
    except smtplib.SMTPAuthenticationError as exc:
        raise Exception(
            "Gmail authentication failed. Check GMAIL_APP_PASSWORD "
            "in your .env or GitHub Secrets."
        ) from exc
    except Exception as gmail_error:
        raise Exception(
            f"Both providers failed. "
            f"Resend: {resend_error_message} | Gmail: {gmail_error}"
        ) from gmail_error
