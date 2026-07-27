from pathlib import Path
from unittest import TestCase


class TestUI6DashboardQAContract(TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.backend = (root / "models/it_management_dashboard.py").read_text(encoding="utf-8")
        cls.js = (root / "static/src/js/it_management_dashboard.js").read_text(encoding="utf-8")
        cls.xml = (root / "static/src/xml/it_management_dashboard.xml").read_text(encoding="utf-8")
        cls.css = (root / "static/src/css/it_management_dashboard.css").read_text(encoding="utf-8")

    def test_accessibility_contract(self):
        for marker in ("aria-label", "aria-live", "aria-busy", "aria-labelledby", "focus-visible", 'tabindex="0"'):
            self.assertIn(marker, self.xml + self.css)
        self.assertIn("preventDefault", self.js)

    def test_responsive_and_reduced_motion_contract(self):
        for marker in ("max-width: 1200px", "max-width: 900px", "max-width: 560px", "prefers-reduced-motion"):
            self.assertIn(marker, self.css)

    def test_request_sequence_and_lazy_sections(self):
        for marker in ("loadSequence", "isCurrentRequest", "sequence === this.loadSequence", "section === this.state.section"):
            self.assertIn(marker, self.js)
        self.assertIn("get_dashboard_data", self.backend)

    def test_bounded_payload_and_query_behavior(self):
        for marker in ("_LIST_LIMIT = 10", "recent_limit", "renewal_limit", "limit=limit", "create_date desc, id desc"):
            self.assertIn(marker, self.backend)
        recent = self.backend[self.backend.index("def _recent_tickets"):self.backend.index("def _renewals_due")]
        self.assertNotIn("description", recent)