from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from idea.cache import CacheStore
from idea.config import load_config
from idea.database import Database
from idea.health import HealthService


class HealthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        raw = json.loads(Path("config/ai4patent.json").read_text(encoding="utf-8"))
        raw["storage"]["database"] = str(root / "idea.db")
        raw["storage"]["cache_dir"] = str(root / "cache")
        raw["storage"]["document_store_dir"] = str(root / "cache" / "documents")
        raw["storage"]["runs_dir"] = str(root / "runs")
        raw["storage"]["uploads_dir"] = str(root / "uploads")
        raw["model"]["auth_file"] = str(root / "auth.json")
        config_path = root / "config.json"
        config_path.write_text(json.dumps(raw), encoding="utf-8")
        self.config = load_config(config_path)
        self.config.model.auth_file.write_text(
            json.dumps({self.config.model.auth_provider: {"apiKey": "test-only"}}),
            encoding="utf-8",
        )
        self.db = Database(self.config.storage.database)
        self.db.initialize()
        self.cache = CacheStore(
            self.config.storage.cache_dir,
            self.db,
            max_bytes=self.config.storage.cache.max_bytes,
            low_watermark_bytes=self.config.storage.cache.low_watermark_bytes,
        )
        self.opencode = root / "opencode"
        self.opencode.write_text("binary", encoding="utf-8")
        self.opencode.chmod(0o755)
        self.opencode_config = root / "opencode.json"
        self.opencode_config.write_text(
            json.dumps({"mcp": {"exa": {"type": "remote"}}}), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def service(self, google_ok=True, recovery=True):
        async def google_probe():
            return google_ok, "fixture"

        return HealthService(
            self.config,
            self.db,
            self.cache,
            opencode_bin=self.opencode,
            opencode_config_path=self.opencode_config,
            google_patents_probe=google_probe,
            workflow_recovery_ready=lambda: recovery,
        )

    def test_all_components_ready(self) -> None:
        result = asyncio.run(self.service().check())
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["components"]["database"]["ok"])
        self.assertTrue(result["components"]["cache"]["ok"])
        self.assertEqual(
            result["components"]["model"]["credential_source"], "auth_file"
        )

    def test_one_online_provider_can_degrade_without_core_failure(self) -> None:
        result = asyncio.run(self.service(google_ok=False).check())
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(result["components"]["exa_mcp"]["ok"])
        self.assertFalse(result["components"]["google_patents_local"]["ok"])

    def test_missing_model_credential_is_core_error(self) -> None:
        self.config.model.auth_file.unlink()
        result = asyncio.run(self.service().check())
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["components"]["model"]["ok"])

    def test_pending_workflow_is_reported_without_hiding_other_health(self) -> None:
        result = asyncio.run(self.service(recovery=False).check())
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["components"]["workflow_recovery"]["status"], "pending")

    def test_health_never_returns_api_key(self) -> None:
        result = asyncio.run(self.service().check())
        rendered = json.dumps(result)
        self.assertNotIn("test-only", rendered)
        self.assertNotIn("apiKey", rendered)


if __name__ == "__main__":
    unittest.main()
