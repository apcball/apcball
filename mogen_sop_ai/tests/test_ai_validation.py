from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.mogen_sop_ai.services.gateway_client import GatewayTimeout


class TestAiValidation(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env.user.groups_id |= self.env.ref("mogen_sop_ai.group_sop_ai_manager")
        self.plan = self.env["mogen.sop.plan"].create({
            "name": "AI Test Plan", "code": "AI-TEST", "company_id": self.env.company.id,
            "date_start": "2026-01-01", "date_end": "2026-12-31",
        })
        self.provider = self.env["mogen.sop.ai.provider"].create({
            "name": "Mock Gateway", "company_id": self.env.company.id,
            "provider_type": "custom", "base_url": "https://gateway.invalid/analysis", "model_name": "mock-model",
        })
        self.template = self.env["mogen.sop.ai.prompt.template"].create({
            "name": "Test Template", "code": "AI_TEST", "company_id": self.env.company.id,
            "analysis_type": "demand", "system_instruction": "Return JSON.",
            "user_prompt_template": "Analyse: {input_snapshot}", "output_schema": "{}", "version": "1.0",
        })

    def _analysis(self):
        return self.env["mogen.sop.ai.analysis"].create({
            "name": "Test analysis", "sop_plan_id": self.plan.id, "company_id": self.env.company.id,
            "analysis_type": "demand", "input_snapshot": '{"period":"2026-01"}',
            "prompt_template_id": self.template.id, "provider_id": self.provider.id,
        })

    def test_valid_mocked_response_creates_proposed_recommendation(self):
        product = self.env["product.product"].create({"name": "AI Product"})
        analysis = self._analysis()
        response = {"summary": "Stock exposure", "recommendations": [{
            "action": "create_purchase_recommendation", "product_id": product.id,
            "quantity": 12.0, "required_date": "2026-09-15", "reason": "Demand exceeds supply.",
        }]}
        with patch("odoo.addons.mogen_sop_ai.services.gateway_client.GatewayClient.invoke", return_value=response):
            analysis.action_queue()
            analysis._process_in_background()
        self.assertEqual(analysis.state, "completed")
        self.assertEqual(analysis.recommendation_ids.state, "proposed")

    def test_invalid_values_and_unsupported_actions_are_rejected(self):
        for response in (
            {"recommendations": [{"action": "create_purchase_recommendation", "product_id": 999999, "quantity": 1}]},
            {"recommendations": [{"action": "create_purchase_recommendation", "quantity": -1}]},
            {"recommendations": [{"action": "confirm_purchase_order", "quantity": 1}]},
            {"recommendations": [{"action": "create_transfer_recommendation", "required_date": "not-a-date", "quantity": 1}]},
        ):
            analysis = self._analysis()
            with patch("odoo.addons.mogen_sop_ai.services.gateway_client.GatewayClient.invoke", return_value=response):
                analysis.action_queue()
                analysis._process_in_background()
            self.assertEqual(analysis.state, "failed")
            self.assertTrue(analysis.validation_errors)

    def test_gateway_timeout_is_retried(self):
        analysis = self._analysis()
        with patch("odoo.addons.mogen_sop_ai.services.gateway_client.GatewayClient.invoke", side_effect=GatewayTimeout("timeout")):
            analysis.action_queue()
            analysis._process_in_background()
        self.assertEqual(analysis.state, "queued")
        self.assertEqual(analysis.retry_count, 1)
