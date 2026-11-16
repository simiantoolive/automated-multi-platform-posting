# Account-linking verification

Observed test result: **69 passed, 1 warning in 3.33s**. The warning is the existing Starlette HTTPX TestClient deprecation notice.

Browser verification at `http://localhost:4000/`:

- Account page loaded in mock mode.
- Connected the five demo accounts using their visible buttons.
- The page displayed `5 / 5 connected`.
- Entered a message containing one CTA URL.
- Selected `Simulate posting to 5 accounts`.
- Results displayed `5 simulated · 0 published`, with all five platforms labelled SIMULATED.

New automated checks cover mock network isolation, missing connections, disconnect, session cookies, CSRF and Origin checks, provider callback parsing, single-use and browser-bound OAuth state, denied authorization, missing owner setup, Bluesky password redaction, expired credentials, and no fallback to owner credentials.

Real provider login and publication were not exercised. No external posts were created.
