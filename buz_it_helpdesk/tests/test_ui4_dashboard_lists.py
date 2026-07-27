from pathlib import Path
from unittest import TestCase


class TestUI4DashboardListsContract(TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.backend = (root / "models/it_management_dashboard.py").read_text(encoding="utf-8")
        cls.js = (root / "static/src/js/it_management_dashboard.js").read_text(encoding="utf-8")
        cls.xml = (root / "static/src/xml/it_management_dashboard.xml").read_text(encoding="utf-8")
        cls.css = (root / "static/src/css/it_management_dashboard.css").read_text(encoding="utf-8")

    def test_recent_tickets_contract_is_bounded_and_deterministic(self):
        for marker in ("_recent_tickets", "recent_limit", "create_date desc, id desc",
                       "ticket_no", "requester", "priority_code", "status_code",
                       "res_model", "res_id"):
            self.assertIn(marker, self.backend)
        self.assertIn("_LIST_LIMIT = 10", self.backend)

    def test_renewals_contract_calculates_days_and_severity(self):
        for marker in ("_renewals_due", "renewal_limit", "new_expiry_date",
                       "license_expiry_date", "days_remaining", "critical",
                       "warning", "attention", "rows.sort(key=lambda row"):
            self.assertIn(marker, self.backend)

    def test_overview_renders_both_lists_and_drills_to_source_records(self):
        for marker in ("recent_tickets", "renewals_due", "Recent Tickets",
                       "Renewals Due", "View all tickets", "View all renewals",
                       "openSource(ticket", "openSource(renewal", "res_id"):
            self.assertIn(marker, self.xml + self.js)

    def test_secret_safe_payload_and_dom_contract(self):
        combined = (self.backend + self.js + self.xml).lower()
        for forbidden in ("license_key", "password", "attachment", "chatter",
                          "mail body", "error_detail", "notification error"):
            self.assertNotIn(forbidden, combined)
        self.assertIn("action_xml_id", self.backend)

    def test_company_filters_and_role_gate_remain_server_side(self):
        self.assertIn("_company_domain", self.backend)
        self.assertIn("_check_access", self.backend)
        self.assertIn("group_it_helpdesk_agent", self.backend)
        self.assertIn("company_id", self.backend)