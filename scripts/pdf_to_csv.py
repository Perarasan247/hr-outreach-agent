"""One-shot converter: data/contacts.pdf -> data/contacts.csv.

Reads a tabular PDF whose columns are SNo, Name, Email, Title,
Company and writes a CSV with columns: name, email, title, company.
Drops the SNo column, lowercases emails, strips whitespace, and
de-duplicates by email.

Run this ONCE before scripts/seed_database.py:

    pip install pdfplumber
    python scripts/pdf_to_csv.py

This script is NOT used at runtime, so pdfplumber is intentionally
not part of requirements.txt.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pdfplumber

PDF_PATH = Path("data/contacts.pdf")
CSV_PATH = Path("data/contacts.csv")


def _is_header(row: list[str]) -> bool:
    """A row is the header if it contains both 'email' and 'name'
    (case-insensitive). The header repeats on every page of a long
    table, so we strip it everywhere we see it.
    """
    lowered = [(c or "").strip().lower() for c in row]
    return "email" in lowered and "name" in lowered


def main() -> None:
    if not PDF_PATH.exists():
        print(f"PDF not found at {PDF_PATH.resolve()}")
        sys.exit(1)

    rows: list[dict] = []
    seen_emails: set[str] = set()
    skipped_no_email = 0
    skipped_duplicate = 0

    with pdfplumber.open(PDF_PATH) as pdf:
        total_pages = len(pdf.pages)
        print(f"Reading {total_pages} pages from {PDF_PATH}...")

        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            for table in tables:
                for raw_row in table:
                    if not raw_row or not any(raw_row):
                        continue
                    if _is_header(raw_row):
                        continue
                    if len(raw_row) < 5:
                        continue

                    # Column order in the PDF: SNo, Name, Email, Title, Company
                    name = (raw_row[1] or "").strip()
                    email = (raw_row[2] or "").strip().lower()
                    title = (raw_row[3] or "").strip()
                    company = (raw_row[4] or "").strip()

                    if not email or "@" not in email:
                        skipped_no_email += 1
                        continue
                    if email in seen_emails:
                        skipped_duplicate += 1
                        continue

                    seen_emails.add(email)
                    rows.append({
                        "name": name,
                        "email": email,
                        "title": title,
                        "company": company,
                    })

            if page_num % 10 == 0 or page_num == total_pages:
                print(f"  page {page_num}/{total_pages} | "
                      f"{len(rows)} rows extracted")

    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["name", "email", "title", "company"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(f"Wrote {len(rows)} contacts to {CSV_PATH}")
    print(f"Skipped (no / invalid email) : {skipped_no_email}")
    print(f"Skipped (duplicate email)    : {skipped_duplicate}")


if __name__ == "__main__":
    main()
