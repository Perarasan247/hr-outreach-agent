"""Prompt template for the brain's analyze_performance() method.

Run once per day, after Phases 1-3 are done. Gemini reviews the
day's stats and recommends adjustments for tomorrow (batch size,
tone, which titles to prioritize).
"""

REFLECTION_PROMPT = """
You are an autonomous outreach agent reviewing your own daily
performance to improve tomorrow's strategy.

TODAY'S STATS:
- Emails sent: {sent}
- Follow-ups sent: {followups_sent}
- Skipped (not worth emailing): {skipped}
- Failed (technical errors): {failed}
- Bounced emails: {bounced}
- Total contacts still pending: {pending_remaining}

Based on these results:
1. Was the batch size right? Too many errors = reduce.
   Zero errors = can increase.
2. High bounce rate means email quality issue or bad addresses.
3. High skip rate means the contact list has many non-HR people.

Recommend tomorrow's strategy.
Batch size must be an integer between 5 and 40.

SPAM TRIGGER WORDS — do not include any of these in your
insights or tone recommendations:
free, guaranteed, urgent, opportunity, winner, congratulations,
click here, act now, limited time, exclusive offer, miracle,
no cost, no obligation, no risk, only $, save big, subscribe,
take action now.

Return ONLY valid JSON, no explanation, no markdown:
{{
  "tone_adjustment": "Keep conversational tone, working well",
  "prioritize_titles": ["Director HR", "VP HR", "Head HR"],
  "recommended_batch_size": 22,
  "insights": "Low bounce rate today. Batch size increased slightly. Skipping non-HR titles more aggressively."
}}
"""
