from odoo.tests.common import TransactionCase


class TestExecutiveService(TransactionCase):
    def test_dashboard_endpoints_return_cached_and_safe_payloads(self):
        service = self.env["mogen.sop.executive.service"]
        self.assertIn("kpis", service.get_executive_kpis())
        self.assertIn("items", service.get_decision_queue())
        self.assertIn("cells", service.get_risk_heatmap())
        self.assertIn("summary", service.get_ai_executive_summary())
