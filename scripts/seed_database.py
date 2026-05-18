"""One-shot loader for data/contacts.csv -> Supabase contacts table.

Run this once before the first agent run. Re-running is safe — it
uses upsert with on_conflict='email', so existing rows are not
overwritten with new statuses.

Expected CSV columns: name, email, title, company
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Allow running from project root: `python scripts/seed_database.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from supabase import create_client  # noqa: E402


CSV_PATH = Path("data/contacts.csv")
BATCH_SIZE = 100


def main() -> None:
    config.validate()

    if not CSV_PATH.exists():
        print(f"CSV not found at {CSV_PATH.resolve()}")
        print("Place your contacts.csv in the data/ folder, then re-run.")
        sys.exit(1)

    print(f"Reading {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)

    expected = {"name", "email", "title", "company"}
    missing_cols = expected - set(df.columns)
    if missing_cols:
        print(f"CSV is missing required columns: {sorted(missing_cols)}")
        sys.exit(1)

    initial_rows = len(df)

    # Strip whitespace on every string field.
    for col in expected:
        df[col] = df[col].astype(str).str.strip()

    # Lowercase emails.
    df["email"] = df["email"].str.lower()

    # Drop rows with missing/empty email.
    df = df[df["email"].notna() & (df["email"] != "") & (df["email"] != "nan")]

    after_email_drop = len(df)
    missing_email_count = initial_rows - after_email_drop

    # Drop duplicate emails (keep the first occurrence).
    df = df.drop_duplicates(subset=["email"], keep="first")
    after_dedupe = len(df)

    # Fill missing title / company with empty string.
    df["title"] = df["title"].replace({"nan": ""}).fillna("")
    df["company"] = df["company"].replace({"nan": ""}).fillna("")
    df["name"] = df["name"].replace({"nan": ""}).fillna("")

    print(f"  initial rows         : {initial_rows}")
    print(f"  dropped (no email)   : {missing_email_count}")
    print(f"  dropped (duplicates) : {after_email_drop - after_dedupe}")
    print(f"  will upsert          : {after_dedupe}")

    if after_dedupe == 0:
        print("Nothing to seed. Exiting.")
        sys.exit(0)

    client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    records = []
    for row in df.itertuples(index=False):
        records.append({
            "name": row.name,
            "email": row.email,
            "title": row.title,
            "company": row.company,
            "status": "pending",
            "followup_count": 0,
        })

    seeded = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i:i + BATCH_SIZE]
        try:
            client.table("contacts").upsert(
                chunk, on_conflict="email"
            ).execute()
            seeded += len(chunk)
            print(f"  upserted {seeded}/{len(records)}")
        except Exception as exc:
            print(f"  batch {i // BATCH_SIZE + 1} failed: {exc}")

    print(f"\nSeeded {seeded} contacts successfully.")
    print(f"Skipped due to missing email: {missing_email_count}")


if __name__ == "__main__":
    main()
