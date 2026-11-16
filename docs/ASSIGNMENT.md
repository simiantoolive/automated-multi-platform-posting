# Assignment interpretation

Source: the email and GitHub assignment screenshots supplied in this conversation. No original assignment file was present in the workspace. This is an implementation checklist, not a verbatim copy of the document.

- Python 3, FastAPI, Uvicorn, Pydantic, HTTPX/Requests, environment-based credentials.
- Original endpoint: `POST http://localhost:4000/posting` with a single `message` field.
- That message includes exactly one valid CTA link and is at most 200 characters. Therefore the limit applies to the full published content, including URL and separating spaces, not just prose.
- The application chooses platforms internally, integrates at least five official APIs, and continues after independent failures.
- Return actual platform status, post URL when available, public access, date/time and errors.
- Provide setup documentation, examples, tests and evidence; publish code in a public repository without credentials.
- The email says 3 hours; the assignment table says 2–3 hours and its submission section says 4 hours. This project avoids optional infrastructure and records the ambiguity rather than claiming a verified time allowance.
- Deadline shown: 22 November 2026. Submission address: hr@chivoxai.com.

The `/posting` route preserves the original input and internal platform selection. `/api/v1/publish` is an additional convenience route requested later: separate `message` and `cta_url`, plus optional `platforms`. It validates the final concatenated content against the same 200-character rule. Omitting platforms attempts all five. Using a subset is useful for setup checks, but a subset is not the full five-platform assignment demonstration.

The prioritised five platforms are Facebook Pages, LinkedIn, X, Mastodon and Bluesky. Unknown accessibility is represented by JSON null rather than an unsupported true/false claim. Mock results have their own status and are never presented as real publication evidence.
