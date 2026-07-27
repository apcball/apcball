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
        cls.css = (root / "static/src/css/it_management_dashboard.css").read_text(encoding="utf-8")

    def test_real_chart_contract_and_svg_are_present(self):
        combined = self.backend + self.helpdesk + self.js + self.xml + self.css
        for marker in (
            "created_resolved", "ticket_backlog", "asset_status",
            "created_count", "resolved_count", "created_domain", "resolved_domain",
            "percentage", "get_chart_data", "<svg", "polyline", "pathLength",
        ):
            self.assertIn(marker, combined)

    def test_empty_and_accessible_chart_states_are_present(self):
        for marker in ("chart_empty", 'role="img"', 'tabindex="0"', "onChartKeydown"):
            self.assertIn(marker, self.xml + self.js)
        self.assertIn("if total else 0.0", self.backend)

    def test_ui3_does_not_add_ui4_or_external_chart_dependency(self):
        combined = (self.backend + self.helpdesk + self.js + self.xml + self.css).lower()
        for forbidden in ("recent tickets", "renewals due", "chart.js", "echarts", "highcharts"):
            self.assertNotIn(forbidden, combined)