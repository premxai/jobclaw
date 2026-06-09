"""Auth middleware posture tests: public reads, locked (fail-closed) writes.

Uses a minimal app with the real APIKeyMiddleware + dummy routes so the test is
isolated from the JobClaw app's database. Skips if FastAPI/httpx aren't installed
(they are in CI's test job)."""

import importlib.util
import os
import unittest

HAVE_DEPS = importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("httpx") is not None

if HAVE_DEPS:
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from api.auth import APIKeyMiddleware

    def _make_client() -> TestClient:
        app = FastAPI()
        app.add_middleware(APIKeyMiddleware)

        @app.get("/jobs")
        def jobs():
            return {"ok": True}

        @app.get("/board/jobs.json")
        def board_jobs():
            return {"ok": True}

        @app.post("/applications")
        def create_app():
            return {"ok": True}

        @app.post("/scraper/trigger")
        def trigger():
            return {"ok": True}

        return TestClient(app)


@unittest.skipUnless(HAVE_DEPS, "fastapi/httpx not installed")
class AuthPostureTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("JOBCLAW_API_KEY")
        os.environ.pop("JOBCLAW_API_KEY", None)
        self.client = _make_client()

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JOBCLAW_API_KEY", None)
        else:
            os.environ["JOBCLAW_API_KEY"] = self._saved

    # --- No key configured (dev / misconfigured prod) ---
    def test_no_key_public_read_allowed(self):
        self.assertEqual(self.client.get("/jobs").status_code, 200)
        self.assertEqual(self.client.get("/board/jobs.json").status_code, 200)

    def test_no_key_write_fails_closed(self):
        # Writes must be disabled (503), never silently open.
        self.assertEqual(self.client.post("/applications").status_code, 503)
        self.assertEqual(self.client.post("/scraper/trigger").status_code, 503)

    # --- Key configured (production) ---
    def test_key_set_public_read_allowed_without_header(self):
        os.environ["JOBCLAW_API_KEY"] = "secret"
        self.assertEqual(self.client.get("/jobs").status_code, 200)
        self.assertEqual(self.client.get("/board/jobs.json").status_code, 200)

    def test_key_set_write_requires_valid_key(self):
        os.environ["JOBCLAW_API_KEY"] = "secret"
        self.assertEqual(self.client.post("/applications").status_code, 401)
        self.assertEqual(self.client.post("/applications", headers={"X-API-Key": "wrong"}).status_code, 401)
        self.assertEqual(self.client.post("/applications", headers={"X-API-Key": "secret"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
