from pathlib import Path
from unittest import TestCase


class TestUI4DashboardListsContract(TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.backend = (root / "models/it_management_dashboard.py").read_text(encoding="utf-8")
        cls.js = (root / "static/src/js/it_management_dashboard.js").read_text(encoding="utf-8")
        cls.xml = (root / "static/src/xml/it_management_dashboard.xml").read_text(encoding="utf-8")

    def test_recent_tickets_contract_is_bounded_and_deterministic(self):
        for marker in ("_recent_tickets", "recent_limit", "create_date desc, id desc", "ticket_no", "requester", "priority_code", "status_code", "res_model", "res_id"):
            self.assertIn(marker, self.backend)
        self.assertIn("_LIST_LIMIT = 10", self.backend)

    def test_asset_lists_are_removed(self):
        self.assertNotIn("renewals_due", self.backend + self.js + self.xml)
        self.assertNotIn("Renewals Due", self.xml)
        self.assertIn("Recent Tickets", self.xml)
