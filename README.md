# Automated Multi-Platform Posting System

A maintainable Python 3.11+ / FastAPI practical-test application that publishes a short message through five official APIs: **Facebook Pages, LinkedIn, X, Mastodon and Bluesky**.

**Verification:** 69 automated tests pass, including browser-session linking and OAuth-response simulations. The local account page was also exercised in a browser: all five demo accounts connected and publishing returned five simulations and zero real posts. **No real social-platform posting or live OAuth flow was tested:** live verification evidence has not been recorded. See [account verification](evidence/accounts-verification.md). One non-failing Starlette test-client deprecation warning is recorded.

## Connect accounts in the browser

Open http://localhost:4000/ for the account-linking page. In mock mode, connect one or more demo accounts, select the destination checkboxes, enter a message containing one URL, then select **Simulate posting**. In real mode, users connect accounts through the browser instead of editing environment tokens. Facebook, LinkedIn, X and Mastodon use OAuth; Bluesky uses a handle and app password. Facebook also asks which Page to use.

The app owner must configure developer client IDs/secrets once. See [browser connection setup](docs/ACCOUNT_CONNECTIONS.md). Connections are held only in server memory for the browser session; restart requires reconnecting. This remains a local single-process demo, not a multi-user hosted product.

## Assignment compatibility

The original screenshot requires `POST /posting` with one message containing exactly one CTA URL and a **200-character maximum for the entire published content**. That route selects all five platforms internally.

The additional `POST /api/v1/publish` accepts separate text and URL fields, with optional platform selection. Its published content is exactly:

```text
message + one space + cta_url
```

The same 200-character limit applies, including all whitespace and the URL. Platform selection is an extension; omit it to attempt all five. See [assignment interpretation](docs/ASSIGNMENT.md), including the conflicting 3/4-hour statements.

## Quick start

PowerShell, from the repository folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 4000
```

If PowerShell blocks activation, use `.\.venv\Scripts\python` instead of `python`; no execution-policy change is necessary.

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 4000
```

- Swagger UI: http://localhost:4000/docs
- OpenAPI: http://localhost:4000/openapi.json
- Health/mode: http://localhost:4000/health

The supplied `.env.example` sets `PUBLISH_MODE=mock`, so copying it provides an offline demo. If no mode is configured, the application defaults to `real` and reports missing credentials honestly. It never silently falls back to simulation. Environment variables take precedence over `.env`; restart the server after changing settings.

For the exact validated dependency versions, install `requirements-lock.txt` instead. Python 3.11+ is required for the per-platform async timeout.

## Requests

### Original assignment endpoint

```powershell
$body = @{ message = 'Explore my practical project https://example.com' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:4000/posting -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 8
```

### Extended endpoint (all five by default)

```json
{
  "message": "Explore my practical project",
  "cta_url": "https://example.com"
}
```

```powershell
$body = @{ message = 'Explore my practical project'; cta_url = 'https://example.com' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:4000/api/v1/publish -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 8
```

For one-account setup checks, add `"platforms": ["mastodon"]`. Allowed names are `facebook`, `linkedin`, `x`, `mastodon`, `bluesky`. Empty, duplicate or unknown selections are rejected. `/posting` does not accept selections.

### Mock response example (one selected platform)

This is a representative simulation response, not publication evidence. The full five-platform response from the actual localhost demo is in [mock-response.json](evidence/mock-response.json).

```json
{
  "request_id": "demo-example",
  "mode": "mock",
  "success": false,
  "success_count": 0,
  "failure_count": 0,
  "simulated_count": 1,
  "total_count": 1,
  "results": [
    {
      "platform": "mastodon",
      "status": "simulated",
      "mode": "mock",
      "post_id": null,
      "posted_url": null,
      "url_source": null,
      "public_access": null,
      "accessibility_verification": "not_checked",
      "date": null,
      "time": null,
      "timestamp_source": null,
      "error": null,
      "warnings": ["MOCK MODE: no API request was made and no post was published."]
    }
  ]
}
```

## Response semantics and validation

- Invalid input returns HTTP **422** with field/model validation details; no provider is called.
- A processed request returns HTTP **200**, even for partial or complete provider failure; inspect the result counts.
- `success` is true only when every selected platform really acknowledged publication. Simulation is counted separately and never increments `success_count`.
- Each real result is `success` or `failed`; mock results are `simulated`.
- Real success timestamps are the service's UTC acknowledgement-processing time, not necessarily the platform's own creation timestamp. Failed/mock results have null publication timestamps.
- `public_access: null` means **unknown**. This implementation does not independently verify anonymous public access. Asking for public visibility is not verification.
- Facebook/Mastodon URLs are accepted only from API responses. X/Bluesky links are derived from validated IDs returned by a successful API call and labelled `derived_from_id`; browser reachability is not claimed.
- LinkedIn returns a post URN. This implementation returns that ID and a null permalink rather than guessing a browser URL.
- A failed Facebook permalink lookup retains the acknowledged publishing success and adds a warning.
- Errors contain a safe code/message, HTTP status when available, numeric Retry-After when available, and an `outcome_unknown` flag. Tokens, raw upstream bodies and request payloads are not logged.
- CTA validation requires one absolute HTTP/HTTPS URL with a qualified hostname or IP address, no embedded credentials or whitespace, and valid URL syntax. It does not fetch the URL or guarantee reachability.
- The extended route requires the URL only in `cta_url`. Embedded scheme-based links and `www.` links in `message` are rejected. Bare domain-looking prose is not automatically converted into a link.
- Length uses Python Unicode code points, not visual grapheme clusters or X's weighted length. Providers may impose additional restrictions; their failures remain isolated.

## Architecture

```text
app/
  main.py                    Application factory, lifecycle and shared HTTPX client
  config.py                  Environment settings and masked secrets
  schemas.py                 Request validation and response contracts
  errors.py                  Safe error classification
  api/routes.py              /posting, /api/v1/publish, /health
  platforms/
    base.py                  Common adapter protocol and HTTP helpers
    facebook.py              Page feed and permalink lookup
    linkedin.py              Versioned Posts API
    x.py                     OAuth 2.0 user-context Posts API
    mastodon.py               Instance status creation
    bluesky.py                Session, post record, UTF-8 CTA facet
    mock.py                  Explicit offline simulation
  services/posting_service.py Concurrent fan-out, counts and safe logging
tests/test_posting.py         Validation and simulated HTTP adapter tests
scripts/verify_demo.py        Starts/stops real Uvicorn and records offline evidence
docs/                        Assignment interpretation and manual setup
evidence/                    Test log, localhost request/response and startup log
```

The service uses `asyncio.gather` and catches each adapter's failure independently. One pooled HTTPX client serves requests. Defaults are 10 seconds per HTTP operation and 35 seconds per adapter, with configurable limits. No automatic publish retries are performed: a timeout can occur after a platform creates a post. Check the account before retrying. Repeated requests can create duplicate posts.

Add a new adapter by implementing the `Platform` protocol, adding its configuration and schema name, and registering it in `ADAPTERS`. Keep provider-specific payloads outside routes.

## Configure real publishing

Follow [platform setup](docs/PLATFORMS.md). Populate only the accounts you intend to use, then set:

```dotenv
PUBLISH_MODE=real
```

Restart Uvicorn and check `/health`. Missing credentials produce independent `missing_configuration` failures. Test one configured account through the extended endpoint before attempting the original five-platform route.

| Platform | What you must supply | Main access dependency | Live-tested here |
|---|---|---|---|
| Facebook Pages | Page ID, Page access token, supported Graph version | Page role/tasks and posting permissions; approval may depend on app usage | No |
| LinkedIn | User access token, person/organization URN, supported API version | Member or organization posting permission and applicable product access | No |
| X | OAuth 2.0 PKCE user access token | Write scopes and current API entitlement/credits | No |
| Mastodon | Instance HTTPS origin and access token | Account on that instance, `write:statuses` permission | No |
| Bluesky | Account PDS origin, handle and app password | Active account and valid app password | No |

The browser page implements OAuth callbacks for Facebook, LinkedIn, X and Mastodon. Developer-account approval, app registration and billing setup remain manual owner prerequisites. Expired connections require reconnection; automatic refresh is not implemented. The original API routes still support environment credentials for assignment compatibility. Never place real credentials in source, screenshots, logs or the public repository.

## Tests and demonstration evidence

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m scripts.verify_demo
```

The tests intercept all third-party HTTP calls using HTTPX MockTransport. They exercise real adapter logic with simulated responses, including success payloads, auth/permission errors, rate limits, transport failures, invalid IDs, timeouts, Unicode URL offsets and partial success. They do **not** certify live API access.

The demo script forces mock mode, starts Uvicorn on an available localhost port, checks Swagger and both publishing routes, checks a 422 overlength response, saves evidence, and terminates its own server. It sends no third-party requests. Generated evidence:

- [pytest.txt](evidence/pytest.txt): 69 passing automated tests, with the recorded dependency warning.
- [verification.json](evidence/verification.json): localhost checks and explicit empty live-platform list.
- [uvicorn-mock.log](evidence/uvicorn-mock.log): actual startup and HTTP activity.
- [mock-request.json](evidence/mock-request.json) and [mock-response.json](evidence/mock-response.json): recorded offline request/response.

For an interview demo: run the server with the copied example configuration, open Swagger, try a valid five-platform request, then try an overlength message. Explain why simulations have no URLs or success count. After obtaining credentials, capture actual live responses and screenshots separately. Record failures and restrictions honestly.

## Known limitations

This is a focused local practical-test service. It has no database, queue, user login, inbound API authentication, distributed rate limiting or persistent idempotency. Keep it on `127.0.0.1`; add authentication and deployment controls before exposing it publicly. It does not scrape websites, bypass platform approval, automate browser posting, upload media, or claim public reachability.

Bluesky uses the configured PDS and an app-password session per request; automatic PDS discovery and session refresh are outside scope. Provider API versions, permissions and billing can change. Facebook metadata retrieval can fail after a successful publish. Unknown outcomes must be checked manually to avoid duplicates.

The tested Starlette release warns that its HTTPX TestClient integration is deprecated. The application still uses the required HTTPX library, and the locked environment passes all tests.

## Upload to GitHub

1. Add live evidence if credentials are available; otherwise clearly keep the documented untested status.
2. Review files and Git history for secrets. `.env`, virtual environments and caches are ignored.
3. Create an empty **public** repository in your GitHub account, without an auto-generated README.
4. From the project folder, run:

```powershell
git status
git add .gitignore .env.example requirements.txt requirements-lock.txt README.md SUBMISSION_EMAIL.md app tests scripts docs evidence
git diff --cached
git commit -m "Implement multi-platform publishing practical"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

If a remote already exists, inspect it with `git remote -v` before changing it. Verify the repository is readable while logged out. Complete [SUBMISSION_EMAIL.md](SUBMISSION_EMAIL.md) with your details and the repository link. Submission deadline in the supplied materials: **22 November 2026**. No repository has been uploaded and no email has been sent by this implementation.
