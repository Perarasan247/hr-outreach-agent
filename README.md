# HR Outreach Agent

An autonomous Python agent that reads HR contacts from a CSV, uses
Google Gemini to reason about each one, writes a personalized cold
outreach email, sends it via Resend (with Gmail SMTP fallback), and
tracks every action in Supabase. Runs automatically on weekday
mornings via GitHub Actions and self-adjusts batch size and tone
based on yesterday's results.

## How It Works

Each weekday at 9:00 AM IST, the agent runs through four phases:

1. **Phase 1 — Final follow-up (day 14):** Re-engages contacts who
   received a first follow-up 14+ days ago. Sends at most 3 final
   nudges per run.
2. **Phase 2 — First follow-up (day 5-7):** Sends a first follow-up
   to contacts who haven't replied after 5 days. Different angle
   from the original — never "just following up". At most 5 per run.
3. **Phase 3 — Fresh outreach:** Pulls the next batch of pending
   contacts, asks Gemini whether to email each one, writes a
   personalized hook + CTA, assembles the full email, and sends.
   Hard-capped at 40 sends per day to protect sender reputation.
4. **Phase 4 — Reflection:** Reviews the day's stats and asks
   Gemini what to change for tomorrow (batch size, tone,
   prioritized titles). Saves the recommendation back to Supabase.

## Prerequisites

- **Python 3.11** locally for the first-run setup.
- **Google Gemini API key** — get one at
  [aistudio.google.com](https://aistudio.google.com/).
- **Resend account** — sign up at [resend.com](https://resend.com)
  and create an API key (free tier = 100 emails/day).
- **Gmail account + App Password** for the fallback sender:
  1. Enable 2-Step Verification on your Google account.
  2. Visit
     [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
  3. Create an App Password named "HR Outreach Agent".
  4. Copy the 16-character password into `GMAIL_APP_PASSWORD`.
- **Supabase account** — free tier at
  [supabase.com](https://supabase.com). Create a new project; copy
  the URL and the `anon` key.
- **GitHub account** with this repo pushed and Actions enabled.

## Database Setup

Open the Supabase SQL editor and paste the SQL below to create the
three tables the agent uses.

```sql
-- contacts: one row per HR contact you might email
CREATE TABLE contacts (
  id                    BIGSERIAL PRIMARY KEY,
  name                  TEXT NOT NULL,
  email                 TEXT UNIQUE NOT NULL,
  title                 TEXT,
  company               TEXT,
  status                TEXT DEFAULT 'pending',
  sent_at               TIMESTAMPTZ,
  followup_1_at         TIMESTAMPTZ,
  followup_2_at         TIMESTAMPTZ,
  followup_count        INTEGER DEFAULT 0,
  email_subject         TEXT,
  email_body            TEXT,
  response_probability  INTEGER,
  skip_reason           TEXT,
  error_message         TEXT,
  sent_via              TEXT,
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- agent_settings: key/value store for the brain's self-adjustments
CREATE TABLE agent_settings (
  id          BIGSERIAL PRIMARY KEY,
  key         TEXT UNIQUE NOT NULL,
  value       JSONB,
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- run_logs: one row per daily run, for performance history
CREATE TABLE run_logs (
  id                 BIGSERIAL PRIMARY KEY,
  run_date           DATE DEFAULT CURRENT_DATE,
  sent_count         INTEGER DEFAULT 0,
  followup_count     INTEGER DEFAULT 0,
  skipped_count      INTEGER DEFAULT 0,
  failed_count       INTEGER DEFAULT 0,
  insights           TEXT,
  recommended_batch  INTEGER,
  created_at         TIMESTAMPTZ DEFAULT NOW()
);
```

## Local Setup

```bash
# 1. Clone
git clone <your-repo-url>
cd hr-outreach-agent

# 2. Virtual env
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 3. Install
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# then open .env and fill in every value

# 5. Seed contacts into Supabase
# Put your contacts.csv at data/contacts.csv first.
# Expected columns: name, email, title, company
python scripts/seed_database.py

# 6. Run the agent once, manually
python agent.py
```

## GitHub Actions Setup

1. Push this repo to GitHub.
2. Go to **Settings → Secrets and variables → Actions → New
   repository secret** and add one secret for each variable in
   `.env.example`:

   - `GEMINI_API_KEY`
   - `RESEND_API_KEY`
   - `GMAIL_ADDRESS`
   - `GMAIL_APP_PASSWORD`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `MY_NAME`
   - `MY_TARGET_ROLE`
   - `MY_EXPERIENCE_YEARS`
   - `MY_KEY_SKILL_1`
   - `MY_KEY_SKILL_2`
   - `MY_KEY_SKILL_3`
   - `MY_CURRENT_PROJECT`
   - `MY_LINKEDIN_URL`
   - `MY_GITHUB_URL`
   - `MY_RESUME_URL`
   - `MY_PHONE`
   - `MY_PORTFOLIO_URL`
   - `MY_INTRO` — full sentence used verbatim as PART 3 of every email
   - `MY_LOOKING_FOR` — comma-separated role list used in PART 4
   - `MY_EMAIL_DISPLAY` (optional — defaults to `GMAIL_ADDRESS`)

3. Enable Actions in the repo (**Settings → Actions → General →
   Allow all actions**).
4. The workflow `.github/workflows/agent.yml` runs Monday-Friday at
   03:30 UTC = **09:00 IST**. You can also trigger it manually:
   **Actions → Agentic HR Outreach → Run workflow**.

## How to Monitor

- **`runs_history.txt`** — appended once per run with a
  human-readable summary (sent count, follow-ups, insights, etc.).
  Created in the repo root and ignored by git, so the GitHub
  Actions runner's copy is ephemeral; for persistent history
  inspect Supabase instead.
- **Supabase `contacts` table** — every contact's current status
  (`pending`, `sent`, `followup_1`, `followup_2`, `stopped`,
  `skipped`, `failed`, `bounced`) lives here. Sort by `sent_at` to
  see what went out today.
- **Supabase `run_logs` table** — one row per daily run, with the
  reflection insights and recommended batch size.
- **GitHub Actions logs** — under the **Actions** tab, click any
  run to see the full console output and the agent's per-contact
  status lines.
- **`agent.log`** — Python `logging` output (debug-level events,
  parse errors, send failures). Created in the working directory.

## Contact Status Reference

| Status        | Meaning                                                 |
| ------------- | ------------------------------------------------------- |
| `pending`     | Not yet processed. The next run may email this contact. |
| `sent`        | First email sent successfully.                          |
| `followup_1`  | First follow-up sent.                                   |
| `followup_2`  | Final follow-up sent. No further emails will go out.    |
| `stopped`     | Agent decided to stop following up gracefully.          |
| `skipped`     | Brain decided not to email (non-HR title, bad email, …).|
| `bounced`     | Recipient address was rejected by both providers.       |
| `failed`      | Technical failure (LLM error, network, etc.).           |
