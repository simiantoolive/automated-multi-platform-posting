# Verification evidence

All evidence in this directory concerns automated HTTP simulations or a localhost server in explicit mock mode. It is not evidence of live social-platform publication.

- `pytest.txt`: final automated test output (69 tests passed; one dependency deprecation warning).
- `verification.json`: actual Uvicorn startup, Swagger, both POST routes, and 422 validation check.
- `uvicorn-mock.log`: server startup and request log from the mock demonstration.
- `mock-request.json`, `mock-response.json`: actual HTTP request/response from that demonstration. Simulated entries have no post URL or publication timestamp.

Live platforms tested: **none**. External posts created: **zero**. Add real responses and screenshots only after obtaining credentials and deliberately completing a live verification. Remove all secrets and private account information before committing evidence.
