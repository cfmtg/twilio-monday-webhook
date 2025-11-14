<!-- .github/copilot-instructions.md
     Guidance for AI coding assistants working in this repository.
     Keep this short, actionable, and specific to this codebase. -->

# Copilot instructions — twilio-monday-webhook

This repository is a tiny serverless webhook that accepts incoming SMS payloads (from Twilio or similar) and posts them to a Monday.com item. The implementation is a single Python/Flask function deployed on Vercel.

Key files
- `api/sms.py` — main Flask app and webhook logic. Read this first to understand data flow.
- `vercel.json` — Vercel build/deploy routing; routes `/sms` → `api/sms.py`.
- `requirements.txt` — runtime dependencies (flask, requests, python-dotenv).

Big-picture architecture
- Single HTTP service (Flask app) exposing: `POST /sms` (webhook) and `GET /` (health). The service:
  - parses incoming JSON with fields like `from`, `body`, `timestamp`;
  - looks up a Monday.com item by phone column using Monday GraphQL API (`items_by_column_values`);
  - posts an update to the matching item (or a configured DEFAULT_ITEM_ID fallback) using a GraphQL mutation.
- The app is intended to be deployed as a serverless function on Vercel (see `vercel.json`), but it can be run locally with Flask for development.

Important repo-specific patterns and conventions
- Environment config: `MONDAY_API_KEY` is read from environment variables. Locally you can use a `.env` file (project has `python-dotenv` listed).
- Constants in `api/sms.py` (e.g. `BOARD_ID`, `DEFAULT_ITEM_ID`, `PHONE_COLUMN_ID`) are hard-coded placeholders — update them before deployment.
- API calls use `requests` and synchronous HTTP/JSON flows (no async).
- Error handling intentionally returns HTTP 200 to Twilio even on internal errors (prevents Twilio retries). If you change that, understand Twilio retry behavior.
- Monday GraphQL queries/mutations are embedded as triple-quoted strings in `api/sms.py` — keep variable interpolation in the separate `variables` dict to avoid injection and to mirror current code style.

Developer workflows (how to run/debug)
- Install deps:
  - python -m pip install -r requirements.txt
- Run locally (PowerShell):
  - $env:MONDAY_API_KEY = "<your-key>"; $env:FLASK_APP = "api.sms"; python -m flask run --port 5000
  - Or run with a `.env` loader if you add a local runner; the code currently does not include an `if __name__ == '__main__'` block.
- Deploy: push to the Vercel-connected repository or use Vercel CLI — `vercel.json` controls that the `api/*.py` builds with `@vercel/python` and routes `/sms` to `api/sms.py`.

Integration points & external dependencies
- Twilio (or any SMS provider) → POST JSON to `/sms` expected shape: `from`, `body`, `timestamp` (the code checks these keys).
- Monday.com GraphQL API at `https://api.monday.com/v2` — uses Bearer-style API key in the `Authorization` header. The code sends queries and mutations with `requests.post(... json={"query":..., "variables":...})`.

Small examples (refer to `api/sms.py`)
- Query template used to locate an item by phone column: `items_by_column_values(board_id:..., column_id:..., column_value:...)`.
- Mutation template used to create an update on an item: `create_update(item_id: Int!, body: String!)`.

Testing & changes to watch for
- There are no automated tests in the repo. When modifying behavior, add small unit tests or a dev-only runner that posts sample payloads to `/sms`.
- Changing the response code to anything other than 200 will cause Twilio to retry by default — intentionally preserved behavior.

Security & operational notes
- Never commit `MONDAY_API_KEY` or real board IDs. Use environment variables and Vercel secrets.
- `DEFAULT_ITEM_ID` and `BOARD_ID` are placeholders in the repo — they must be set to real IDs in production.

If you change the API shape
- Update the parsing logic in `api/sms.py` and update any callers (Twilio webhook config). Keep the same defensive checks (verify `from` and `body`) unless you intentionally allow other shapes.

When editing, reference these lines in `api/sms.py`:
- lookup query: the `items_by_column_values` query near the top of `receive_sms()`.
- mutation: the `create_update` mutation further down in `receive_sms()`.

If anything here is unclear or missing, tell me what you want added (examples, run commands, or secrets handling), and I will update this file.
