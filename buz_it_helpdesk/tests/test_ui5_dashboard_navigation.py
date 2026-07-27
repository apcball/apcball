from pathlib import Path
from unittest import TestCase


class TestUI5DashboardNavigationContract(TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.backend = (root / "models/it_management_dashboard.py").read_text(encoding="utf-8")
        cls.js = (root / "static/src/js/it_management_dashboard.js").read_text(encoding="utf-8")
        cls.xml = (root / "static/src/xml/it_management_dashboard.xml").read_text(encoding="utf-8")

    def test_server_role_matrix_and_manager_only_settings(self):
        for marker in (
            "def _navigation", "has_group", "group_it_helpdesk_agent",
            "group_it_asset_user", "group_it_helpdesk_manager",
            '"key": "overview"', '"key": "helpdesk"',
            '"key": "assets"', '"key": "licenses"',
            '"key": "renewals"', '"key": "reports"', '"key": "settings"',
        ):
            self.assertIn(marker, self.backend)
        self.assertIn("if is_manager:", self.backend)

    def test_action_ids_and_domains_are_server_provided(self):
        for marker in (
            "action_helpdesk_report",
            "action_buz_it_asset_software_licenses",
            "action_buz_it_asset_renewals",
            "action_helpdesk_categories",
            '"domain": [["asset_type", "=", "software_license"]]',
            '"action_xml_id"',
        ):
            self.assertIn(marker, self.backend)

    def test_sections_keep_existing_dashboard_subcomponents(self):
        self.assertIn('state.section == "helpdesk"', self.js)
        self.assertIn('state.section == "asset"', self.js)
        self.assertIn('HelpdeskDashboard', self.js + self.xml)
        self.assertIn("selectSection(item.section)", self.js)

    def test_keyboard_navigation_and_collapse_do_not_use_business_storage(self):
        for marker in ('<button type="button" class="o_it_management_nav"',
                       't-on-click="() => openNavigation(item)"',
                       "toggleSidebar", "sidebarCollapsed", "t-att-aria-label"):
            self.assertIn(marker, self.xml + self.js)
        self.assertNotIn("localStorage", self.js)
        self.assertNotIn("sessionStorage", self.js)