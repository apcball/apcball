from pathlib import Path
from unittest import TestCase


class TestUI1DashboardShell(TestCase):
    """Static UI-1 contract checks; no business data or workflow is changed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.module_root = Path(__file__).resolve().parents[1]
        cls.js = (cls.module_root / "static/src/js/it_management_dashboard.js").read_text(encoding="utf-8")
        cls.xml = (cls.module_root / "static/src/xml/it_management_dashboard.xml").read_text(encoding="utf-8")
        cls.css = (cls.module_root / "static/src/css/it_management_dashboard.css").read_text(encoding="utf-8")

    def test_shell_states_and_stale_response_contract_are_present(self):
        for marker in ("loadSequence", "lastUpdated", "async refresh", "toggleSidebar", "hasData"):
            self.assertIn(marker, self.js)
        for marker in ("o_it_management_sidebar", "o_it_management_filter_bar", "o_it_management_loading", "o_it_management_error", "o_it_management_empty"):
            self.assertIn(marker, self.xml)
        self.assertIn("sequence === this.loadSequence", self.js)

    def test_design_tokens_and_responsive_shell_are_present(self):
        for marker in ("--it-color-primary", "--it-space-4", "--it-radius-lg", "@media (max-width: 760px)", "grid-template-columns", "o_it_management_skeleton"):
            self.assertIn(marker, self.css)

    def test_ui1_shell_contract_remains_present_after_later_chart_phases(self):
        for marker in ("o_it_management_dashboard", "o_it_management_sidebar", "o_it_management_filter_bar"):
            self.assertIn(marker, self.xml)
        self.assertIn("loadSequence", self.js)