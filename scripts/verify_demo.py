"""Start a real Uvicorn process in MOCK mode, exercise HTTP routes, save evidence, stop it."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"


def main():
    EVIDENCE.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["PUBLISH_MODE"] = "mock"  # Never publish externally from this verification script.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)]
    with (EVIDENCE / "uvicorn-mock.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            with httpx.Client(base_url=base, timeout=3, trust_env=False) as client:
                for attempt in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Uvicorn exited; inspect evidence/uvicorn-mock.log")
                    try:
                        health = client.get("/health")
                        if health.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Uvicorn did not become ready")
                assert health.json() == {"status": "ok", "mode": "mock"}
                assert client.get("/docs").status_code == 200
                assert client.get("/openapi.json").status_code == 200
                body = {"message": "Explore my practical project", "cta_url": "https://example.com"}
                response = client.post("/api/v1/publish", json=body)
                assert response.status_code == 200
                result = response.json()
                assert result["mode"] == "mock" and result["simulated_count"] == 5
                assert result["success_count"] == 0 and result["success"] is False
                assert all(item["posted_url"] is None for item in result["results"])
                (EVIDENCE / "mock-request.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
                (EVIDENCE / "mock-response.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                assignment = client.post("/posting", json={"message": "Explore my project https://example.com"})
                assert assignment.status_code == 200 and assignment.json()["simulated_count"] == 5
                invalid = client.post("/api/v1/publish", json={"message": "a" * 200, "cta_url": "https://example.com"})
                assert invalid.status_code == 422
                report = {"mode": "mock", "server_started": True, "health": health.json(),
                          "swagger_status": 200, "publish_status": response.status_code,
                          "assignment_status": assignment.status_code,
                          "overlength_status": invalid.status_code,
                          "external_posts_created": 0, "live_platforms_tested": []}
                (EVIDENCE / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(json.dumps(report, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
