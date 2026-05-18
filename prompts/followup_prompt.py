"""Prompt template for the brain's decide_followup() method.

Asks Gemini whether to send a follow-up and (if so) produces the
opening hook + CTA for it. The body is then assembled by
email_tool._build_email_body using the same 7-part template.
"""

FOLLOWUP_PROMPT = """
You sent a job outreach email {days_since_sent} days ago.
No reply received. Decide whether and how to follow up.

ORIGINAL EMAIL:
Subject: {original_subject}
Body: {original_body}

RECIPIENT:
- Name: {name}
- Title: {title}
- Company: {company}
- Follow-up number this would be: {followup_number}

RULES:
- Follow-up 1 (day 5-7): Short, different angle, add new value
  (mention a skill, a project, or something relevant to them).
- Follow-up 2 (day 14): Very short, graceful last attempt; make
  it easy for them to say no.
- Never a 3rd follow-up — if followup_number > 2, always stop.
- Each follow-up must feel completely different from the last.
- Never say "just following up" or "bumping this".

YOU ARE WRITING ONLY THREE THINGS WHEN ACTION IS NOT "stop":
  1. subject       — under 45 characters, conversational
  2. opening_hook  — 1-2 sentences. New angle vs. the original.
                     Reference {company} naturally.
  3. cta           — one sentence. Soft, easy to say no.

DO NOT write greeting, who-I-am paragraph, signature, or P.S.

Decide action:
- "followup": send follow-up 1
- "final_followup": send follow-up 2 (last one)
- "stop": do not send, give up gracefully (subject/hook/cta can
  be empty strings in this case)

SPAM TRIGGER WORDS — NEVER USE ANY OF THESE:
free, guaranteed, winner, urgent, act now, limited time,
exclusive offer, click here, earn money, opportunity,
apply now, immediate, congratulations, you have been selected,
unsubscribe, miracle, money back, bonus, no cost, no obligation,
no risk, only $, save big, subscribe, take action now.

Return ONLY valid JSON, no explanation, no markdown:
{{
  "action": "followup",
  "reason": "Day 6, first follow-up appropriate",
  "subject": "...",
  "opening_hook": "...",
  "cta": "..."
}}
"""
