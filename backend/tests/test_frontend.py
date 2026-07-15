from __future__ import annotations

import re
import unittest
from pathlib import Path


class FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = Path("frontend/index.html").read_text(encoding="utf-8")
        cls.javascript = Path("frontend/app.js").read_text(encoding="utf-8")
        cls.css = Path("frontend/style.css").read_text(encoding="utf-8")

    def test_only_idea_workflow_is_visible_and_generic_agent_endpoint_is_absent(self) -> None:
        self.assertIn("IDEA 专利评估工作台", self.html)
        for legacy in ("5 大专利模块", "业界专利分析", "PCT申请评审", "侵权挖掘"):
            self.assertNotIn(legacy, self.html)
        self.assertNotIn('"/api/run"', self.javascript)

    def test_frontend_calls_durable_idea_history_progress_and_report_apis(self) -> None:
        for fragment in (
            "/api/idea/cases",
            "/events",
            "/report",
            "/rerun",
            "/cancel",
        ):
            self.assertIn(fragment, self.javascript)
        for step in (
            "PREPARE_INPUT",
            "RETRIEVE_CANDIDATES",
            "ANALYZE_DOCUMENTS",
            "DETERMINE_NOVELTY",
            "AUDIT_AND_REPORT",
        ):
            self.assertIn(step, self.javascript)

    def test_all_javascript_dom_ids_exist_and_external_data_uses_text_content(self) -> None:
        html_ids = set(re.findall(r'\bid="([^"]+)"', self.html))
        referenced = set(re.findall(r'\$\("([A-Za-z][A-Za-z0-9_-]*)"\)', self.javascript))
        self.assertEqual(referenced - html_ids, set())
        self.assertNotIn(".innerHTML", self.javascript)

    def test_responsive_three_column_layout_and_budget_controls_exist(self) -> None:
        self.assertIn("grid-template-columns:", self.css)
        self.assertIn("@media (max-width: 760px)", self.css)
        for control in ("candidateMax", "deepMin", "deepMax", "searchMode"):
            self.assertIn(f'id="{control}"', self.html)
        self.assertIn('min="10"', self.html)


if __name__ == "__main__":
    unittest.main()
