from pathlib import Path
from unittest import TestCase


class TestUI7RegressionContract(TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.backend = (root / "models/it_management_dashboard.py").read_text(encoding="utf-8")
        cls.js = (root / "static/src/js/it_management_dashboard.js").read_text(encoding="utf-8")
        cls.xml = (root / "static/src/xml/it_management_dashboard.xml").read_text(encoding="utf-8")
        cls.css = (root / "static/src/css/it_management_dashboard.css").read_text(encoding="utf-8")

    def test_regression_suites_cover_helpdesk_asset_renewal_dashboard(self):
        tests = Path(__file__).parent
        for name in (
            "test_helpdesk_ticket.py",
            "test_it_asset.py",
            "test_it_asset_renewal.py",
            "test_it_management_dashboard.py",
            "test_phase_7_regression_security.py",
        ):
            self.assertTrue((tests / name).exists(), name)

    def test_xml_owl_javascript_dom_contract(self):
        for marker in (
            't-name="buz_it_helpdesk.ItManagementDashboard"',
            'registry.category("actions")',
            "HelpdeskDashboard",
            "state.section == 'overview'",
            "state.section == 'asset'",
            "openSource",
            "recentTickets",
            "renewalsDue",
            "t-on-click",
        ):
            self.assertIn(marker, self.xml + self.js)
        self.assertNotIn('id=" it-management-title', self.xml)

    def test_role_matrix_and_multi_company_boundary(self):
        for marker in (
            "_check_access",
            "group_it_helpdesk_agent",
            "group_it_helpdesk_manager",
            "env.companies",
            "company_id",
            "get_dashboard_data",
        ):
            self.assertIn(marker, self.backend)

    def test_rpc_payload_drilldown_and_secret_safety(self):
        for marker in ("res_model", "res_id", "domain", "action.doAction"):
            self.assertIn(marker, self.backend + self.js)
        payload_text = (self.backend + self.js + self.xml).lower()
        for forbidden in (
            "license_key",
            "password",
            "attachment",
            "chatter",
            "mail body",
            "error_detail",
            "notification error",
        ):
            self.assertNotIn(forbidden, payload_text)

    def test_ui6_keyboard_and_stale_response_regression(self):
        for marker in ("onRowKeydown", "preventDefault", "isCurrentRequest", "loadSequence"):
            self.assertIn(marker, self.js)
        self.assertIn("onRowKeydown(event, ticket", self.xml)
        self.assertIn("onRowKeydown(event, renewal", self.xml)
        self.assertNotIn("localStorage", self.js)
        self.assertNotIn("sessionStorage", self.js)