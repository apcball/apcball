"""Strict validation for untrusted AI structured responses."""

import json
from datetime import datetime

from odoo import _
from odoo.exceptions import AccessError, ValidationError


ALLOWED_ACTIONS = {
    "create_purchase_recommendation": "purchase",
    "create_manufacturing_recommendation": "manufacture",
    "create_transfer_recommendation": "transfer",
    "create_forecast_adjustment_recommendation": "forecast_adjustment",
    "create_risk_mitigation_recommendation": "warning",
    "request_scenario_simulation": "warning",
    "generate_management_summary": "warning",
}
PRODUCT_ACTIONS = {
    "create_purchase_recommendation",
    "create_manufacturing_recommendation",
    "create_transfer_recommendation",
    "create_forecast_adjustment_recommendation",
}


class StructuredResponseValidator:
    """Validate JSON shape, values, Odoo IDs, and requester record access."""

    def __init__(self, analysis):
        self.analysis = analysis
        self.env = analysis.env(user=analysis.requested_by_id.id)

    def _record(self, model_name, record_id, label):
        if not isinstance(record_id, int) or record_id <= 0:
            raise ValidationError(_("%(label)s ID must be a positive integer.", label=label))
        record = self.env[model_name].browse(record_id).exists()
        if not record:
            raise ValidationError(_("%(label)s ID %(id)s does not exist.", label=label, id=record_id))
        try:
            record.check_access_rights("read")
            record.check_access_rule("read")
        except AccessError as error:
            raise ValidationError(_("You cannot access %(label)s ID %(id)s.", label=label, id=record_id)) from error
        return record

    @staticmethod
    def _date(value):
        if value in (None, False, ""):
            return False
        if not isinstance(value, str):
            raise ValidationError(_("Required date must be an ISO date string."))
        try:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        except ValueError as error:
            raise ValidationError(_("Required date must use YYYY-MM-DD.")) from error

    def validate(self, payload):
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as error:
                raise ValidationError(_("AI response is not valid JSON.")) from error
        if not isinstance(payload, dict):
            raise ValidationError(_("AI response must be a JSON object."))
        recommendations = payload.get("recommendations", [])
        if not isinstance(recommendations, list):
            raise ValidationError(_("AI recommendations must be a JSON array."))
        normalized = []
        for item in recommendations:
            if not isinstance(item, dict):
                raise ValidationError(_("Each AI recommendation must be a JSON object."))
            action = item.get("action")
            if action not in ALLOWED_ACTIONS:
                raise ValidationError(_("AI action '%(action)s' is not allowed.", action=action))
            quantity = item.get("quantity", 0.0)
            if not isinstance(quantity, (int, float)) or isinstance(quantity, bool) or quantity < 0:
                raise ValidationError(_("AI recommendation quantities must be non-negative numbers."))
            product_id = item.get("product_id")
            warehouse_id = item.get("warehouse_id")
            if action in PRODUCT_ACTIONS and not product_id:
                raise ValidationError(_("Product ID is required for %(action)s.", action=action))
            if product_id:
                self._record("product.product", product_id, _("Product"))
            if warehouse_id:
                self._record("stock.warehouse", warehouse_id, _("Warehouse"))
            if action == "create_transfer_recommendation" and not warehouse_id:
                raise ValidationError(_("Warehouse ID is required for a transfer recommendation."))
            scenario_id = item.get("scenario_id")
            if scenario_id:
                self._record("mogen.sop.scenario", scenario_id, _("Scenario"))
            normalized.append({
                "action": action,
                "recommendation_type": ALLOWED_ACTIONS[action],
                "product_id": product_id or False,
                "warehouse_id": warehouse_id or False,
                "quantity": float(quantity),
                "required_date": self._date(item.get("required_date")),
                "title": item.get("title") or action.replace("_", " ").title(),
                "description": item.get("description") or item.get("summary") or "",
                "reason": item.get("reason") or "",
                "expected_impact": item.get("expected_impact") or "",
                "priority": item.get("priority", "normal"),
                "source_references": {key: item[key] for key in ("product_id", "warehouse_id", "scenario_id") if item.get(key)},
            })
        return payload, normalized
