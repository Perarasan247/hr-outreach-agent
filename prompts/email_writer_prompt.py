"""Prompt template for the brain's write_email() method.

Asks Gemini for ONLY two creative pieces — the opening hook (which
references the recipient's company) and the soft CTA. The rest of
the email body (greeting, who-I-am paragraph, the ask, signature,
P.S.) is assembled deterministically by email_tool._build_email_body.
"""

EMAIL_WRITER_PROMPT = """
Write the creative parts of a cold outreach email from a job
seeker to an HR professional.

SENDER PROFILE:
- Name: {my_name}
- Target Role: {my_target_role}
- Experience: {my_experience_years} years
- Key skills: {my_key_skill_1}, {my_key_skill_2}, {my_key_skill_3}
- Current project: {my_current_project}

RECIPIENT:
- Name: {name}
- Title: {title}
- Company: {company}

STRATEGY:
- Tone: {tone}
- Angle: {angle}

YOU ARE WRITING ONLY THREE THINGS:
  1. subject       — under 45 characters, conversational. MUST be
                     about the recipient or their company — never
                     starts with the sender's name. NEVER include
                     "{my_name}" anywhere in the subject. Examples
                     that are GOOD: "Quick question about {company}",
                     "Open roles at {company}?", "Hello from a fan
                     of {company}'s work". Examples that are BAD:
                     "{my_name} for X at {company}", "{my_name}
                     looking for AI roles".
  2. opening_hook  — 1-2 sentences that reference {company}
                     specifically. Make it feel researched, not
                     generic. Sound like a human typing at 9am.
  3. cta           — exactly one sentence. EITHER suggest a brief
                     chat (do NOT specify what the chat would be
                     about — keep it open, e.g. "Would you have
                     10 minutes to connect this week?" or "Open
                     to a short call sometime soon?") OR ask if
                     they'd be open to having a look at your
                     resume. Never both. Never pushy. NEVER write
                     "chat about my X" or "discuss my Y" — keep
                     the topic open so the recipient picks it.

DO NOT write a greeting, who-I-am paragraph, the ask, signature,
or P.S. — those are added automatically.

STRICT RULES:
1. opening_hook must NOT be "I hope this email finds you well"
2. opening_hook must NOT be "I wanted to reach out"
3. opening_hook references {company} once, naturally
4. Subject line under 45 characters
5. Subject line is NOT all caps, has at most one "?" or ".", and
   no exclamation marks
6. No buzzwords: synergy, leverage, passionate, rockstar, ninja
7. Write in {tone} tone

SPAM TRIGGER WORDS — NEVER USE ANY OF THESE:
Subject line: free, guaranteed, winner, urgent, act now,
  limited time, exclusive offer, click here, earn money,
  make money, opportunity, apply now, immediate,
  important notice, attention, open immediately,
  congratulations, you have been selected, dear friend.

Body text: dear [generic title], to whom it may concern,
  this is not spam, you have been selected, unsubscribe,
  click below, visit our website, buy now, order now,
  call now, FREE!, $$$, 100% satisfied, best price, bonus,
  cash, cheap, miracle, money back, no cost, no obligation,
  no risk, only $, save big, subscribe, take action now,
  trial, unlimited, winner, you have been chosen.

Return ONLY valid JSON, no explanation, no markdown:
{{
  "subject": "Quick question, {name}",
  "opening_hook": "I noticed {company} has been ... ",
  "cta": "Would you be open to a quick 10-minute call this week?"
}}
"""
