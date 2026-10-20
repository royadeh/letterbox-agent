# Letterbox

Agent that explains dense official letters in plain language (English and Persian),
lists the reader's options, and drafts a reply. General information only, not legal or tax advice.
Input: official letters in English. Output: plain-language explanation in English and Farsi. Reply drafts are in English, with a Farsi explanation.
## Commands
- Test: `pytest -q`
- Eval: `python -m eval.run` (calls a real model; not run in CI)

## Rules
- Write a failing test before each feature. Tests use fake LLM responses: no API key, no network.
- Never change a test just to make it pass; tell me if a test seems wrong.
- Type hints everywhere; keep functions small.
- LLM output is parsed into Pydantic models and validated. If validation fails, retry once, then answer "I'm not sure".
- Every extracted fact must carry the exact sentence from the letter that supports it, and a verify step must check that sentence appears in the letter.
- Read API keys from environment variables only. Never hardcode keys or commit `.env`.
- Use only synthetic letters. No real names, account numbers or ID numbers anywhere in the repo.
- Never guess a deadline or amount. If unsure, say so and tell the reader to check with the sender.
- After each change, explain in under 10 lines, in plain language, what changed and why.
- Commit after each working feature.

