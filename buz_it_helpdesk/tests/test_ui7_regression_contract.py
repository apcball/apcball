from pathlib import Path
from unittest import TestCase


class TestUI7RegressionContract(TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.backend = (root / "models/it_management_dashboard.py").read_text(encoding="utf-8")
        cls.js = (root / "static/src/js/it_management_dashboard.js").read_text(encoding="utf-8")
        cls.xml = (root / "static/src/xml/it_management_dashboard.xml").read_text(encoding="utf-8")

    def test_dashboard_contract_is_helpdesk_only(self):
        combined = self.backend[self.backend.index("def _check_access"):] + self.js + self.xml
        for marker in ("ItManagementDashboard", "HelpdeskDashboard", "state.section == 'overview'", "state.section == 'helpdesk'", "openSource", "recentTickets", "Created vs Resolved", "Ticket Backlog"):
            self.assertIn(marker, combined)
        for forbidden in ("buz.it.asset", "asset_status", "renewals_due", "license_key", "password"):
            self.assertNotIn(forbidden, combined.lower())

    def test_rpc_payload_drilldown_and_stale_response_contract(self):
        for marker in ("res_model", "res_id", "domain", "action.doAction", "isCurrentRequest", "loadSequence", "preventDefault"):
            self.assertIn(marker, self.backend + self.js)
        self.assertNotIn("localStorage", self.js)
        self.assertNotIn("sessionStorage", self.js)
