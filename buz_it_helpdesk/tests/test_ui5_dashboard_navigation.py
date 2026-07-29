from pathlib import Path
from unittest import TestCase


class TestUI5DashboardNavigationContract(TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.backend = (root / "models/it_management_dashboard.py").read_text(encoding="utf-8")
        cls.js = (root / "static/src/js/it_management_dashboard.js").read_text(encoding="utf-8")
        cls.xml = (root / "static/src/xml/it_management_dashboard.xml").read_text(encoding="utf-8")

    def test_navigation_contains_only_helpdesk(self):
        self.assertNotIn('"section": "overview"', self.backend)
        self.assertIn('"section": "helpdesk"', self.backend)
        self.assertNotIn('"section": "asset"', self.backend + self.js + self.xml)
        self.assertNotIn("group_it_asset", self.backend + self.xml)

    def test_navigation_is_server_provided_and_keyboard_safe(self):
        for marker in ("action_xml_id", "selectSection(item.section)", "toggleSidebar", "sidebarCollapsed", "onChartKeydown"):
            self.assertIn(marker, self.backend + self.js + self.xml)
