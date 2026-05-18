"""Configuration loader for the HR Outreach Agent.

Loads all environment variables via python-dotenv, exposes them as
module-level constants, defines behavioral constants, and provides a
validate() helper that exits cleanly when required variables are
missing.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


# ─── API Keys ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# ─── Gmail (fallback sender) ───────────────────────────────────────
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# ─── Supabase ──────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ─── Sender Profile ────────────────────────────────────────────────
MY_NAME = os.getenv("MY_NAME")
MY_TARGET_ROLE = os.getenv("MY_TARGET_ROLE")
MY_EXPERIENCE_YEARS = os.getenv("MY_EXPERIENCE_YEARS")
MY_KEY_SKILL_1 = os.getenv("MY_KEY_SKILL_1")
MY_KEY_SKILL_2 = os.getenv("MY_KEY_SKILL_2")
MY_KEY_SKILL_3 = os.getenv("MY_KEY_SKILL_3")
MY_CURRENT_PROJECT = os.getenv("MY_CURRENT_PROJECT")
MY_LINKEDIN_URL = os.getenv("MY_LINKEDIN_URL")
MY_GITHUB_URL = os.getenv("MY_GITHUB_URL")
MY_RESUME_URL = os.getenv("MY_RESUME_URL")
MY_PHONE = os.getenv("MY_PHONE")
MY_PORTFOLIO_URL = os.getenv("MY_PORTFOLIO_URL")

# Free-form template parts written by the sender, used verbatim in
# the static body. MY_INTRO replaces the old hard-coded "who I am"
# paragraph; MY_LOOKING_FOR is dropped into the role-search line.
MY_INTRO = os.getenv("MY_INTRO")
MY_LOOKING_FOR = os.getenv("MY_LOOKING_FOR")

# Display email — falls back to GMAIL_ADDRESS if not set.
MY_EMAIL_DISPLAY = os.getenv("MY_EMAIL_DISPLAY") or GMAIL_ADDRESS


# ─── Behavioral constants ──────────────────────────────────────────
BATCH_SIZE_DEFAULT = 35
BATCH_SIZE_MIN = 25
BATCH_SIZE_MAX = 40

DELAY_MIN_SECONDS = 45
DELAY_MAX_SECONDS = 120

FOLLOWUP_1_AFTER_DAYS = 5
FOLLOWUP_2_AFTER_DAYS = 14
MAX_FOLLOWUPS = 2

DAILY_SEND_LIMIT = 40
RESEND_DAILY_LIMIT = 100


# ─── Required env vars for validate() ──────────────────────────────
REQUIRED_VARS = {
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "RESEND_API_KEY": RESEND_API_KEY,
    "GMAIL_ADDRESS": GMAIL_ADDRESS,
    "GMAIL_APP_PASSWORD": GMAIL_APP_PASSWORD,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
    "MY_NAME": MY_NAME,
    "MY_TARGET_ROLE": MY_TARGET_ROLE,
    "MY_EXPERIENCE_YEARS": MY_EXPERIENCE_YEARS,
    "MY_KEY_SKILL_1": MY_KEY_SKILL_1,
    "MY_KEY_SKILL_2": MY_KEY_SKILL_2,
    "MY_KEY_SKILL_3": MY_KEY_SKILL_3,
    "MY_CURRENT_PROJECT": MY_CURRENT_PROJECT,
    "MY_LINKEDIN_URL": MY_LINKEDIN_URL,
    "MY_GITHUB_URL": MY_GITHUB_URL,
    "MY_RESUME_URL": MY_RESUME_URL,
    "MY_PHONE": MY_PHONE,
    "MY_PORTFOLIO_URL": MY_PORTFOLIO_URL,
    "MY_INTRO": MY_INTRO,
    "MY_LOOKING_FOR": MY_LOOKING_FOR,
}


def validate() -> None:
    """Validate that every required env var is present.

    Prints the missing variable names and exits with status 1 if any
    are absent.
    """
    missing = [name for name, value in REQUIRED_VARS.items() if not value]
    if missing:
        print("Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nSet these in your .env file or GitHub Actions secrets, "
              "then re-run.")
        sys.exit(1)
