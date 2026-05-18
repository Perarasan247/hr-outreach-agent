"""Prompt template for the brain's decide_strategy() method.

Asks Gemini to reason about a single HR contact and decide whether
to send, what tone to use, what angle to take, and what the
realistic response probability is. Output is strict JSON.
"""

DECISION_PROMPT = """
You are an autonomous job outreach agent. Your goal is to help
{my_name} find job opportunities by emailing HR professionals.

Analyze this HR contact and decide if and how to reach out:

Contact Details:
- Name: {name}
- Title: {title}
- Company: {company}
- Email: {email}

Today: {today}
Target role for {my_name}: {target_role}

Think step by step:
1. Is this a real HR decision maker? (Director/VP/Head = good,
   junior recruiter = okay, non-HR title = skip)
2. Is the email domain professional and valid-looking?
3. What angle works best for this person's seniority?
4. What tone matches their likely communication style?
5. What is the realistic chance they respond?

Red flags that mean skip (set should_send to false):
- Title has nothing to do with HR or recruitment
- Email looks like a generic info@ or admin@ address
- Company name is unclear or suspicious

SPAM TRIGGER WORDS — NEVER USE ANY OF THESE IN ANY OUTPUT:
Subject line: free, guaranteed, winner, urgent, act now,
  limited time, exclusive offer, click here, earn money,
  make money, work from home, risk free, no obligation,
  congratulations, you have been selected, dear friend,
  this is not spam, opportunity, apply now, immediate,
  important notice, attention, open immediately

Body text: dear [generic title], to whom it may concern,
  this is not spam, you have been selected, unsubscribe,
  click below, visit our website, buy now, order now,
  call now, FREE!, $$$, 100% satisfied, best price, bonus,
  cash, cheap, miracle, money back, no cost, no obligation,
  no risk, only $, save big, subscribe, take action now,
  trial, unlimited, winner, you have been chosen.

Return ONLY valid JSON, no explanation, no markdown:
{{
  "should_send": true,
  "send_reason": "VP-level HR at a mid-size tech company, good match for {target_role}",
  "tone": "conversational",
  "angle": "job-opportunity",
  "red_flags": [],
  "response_probability": 65,
  "skip_reason": ""
}}
"""
