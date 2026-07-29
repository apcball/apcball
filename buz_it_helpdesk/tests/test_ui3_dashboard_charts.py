from pathlib import Path
from unittest import TestCase


class TestUI3DashboardChartsContract(TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.backend = (root / "models/it_management_dashboard.py").read_text(encoding="utf-8")
        cls.helpdesk = (root / "models/helpdesk_dashboard.py").read_text(encoding="utf-8")
        cls.js = (root / "static/src/js/it_management_dashboard.js").read_text(encoding="utf-8")
        cls.xml = (root / "static/src/xml/it_management_dashboard.xml").read_text(encoding="utf-8")

    def test_helpdesk_chart_contract_and_svg_are_present(self):
        combined = self.backend + self.helpdesk + self.js + self.xml
        for marker in ("created_resolved", "ticket_backlog", "created_count", "resolved_count", "created_domain", "resolved_domain", "get_chart_data", "<svg", "polyline"):
            self.assertIn(marker, combined)
        self.assertNotIn("asset_status", combined)

    def test_empty_and_accessible_chart_states_are_present(self):
        for marker in ("chart_empty", 'role="img"', 'tabindex="0"', "onChartKeydown"):
            self.assertIn(marker, self.xml + self.js)
