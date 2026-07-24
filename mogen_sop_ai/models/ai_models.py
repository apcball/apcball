"""Auditable AI gateway configuration, analyses, and recommendation workflow."""

import hashlib
import json
import os
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services.gateway_client import GatewayClient, GatewayError
from ..services.response_validator import ALLOWED_ACTIONS, StructuredResponseValidator


REFERENCE_PATTERN = re.compile(r"^(env:[A-Z][A-Z0-9_]*|config:mogen_sop_ai\.[A-Za-z0-9_.-]+)$")


class MogenSopAiProvider(models.Model):
    _name = "mogen.sop.ai.provider"
    _description = "S&OP AI Gateway Provider"
    _check_company_auto = True
    _order = "company_id, name"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    provider_type = fields.Selection([("hermes", "Hermes"), ("openrouter", "OpenRouter Compatible"), ("custom", "Custom Gateway")], required=True, default="hermes")
    base_url = fields.Char(required=True)
    model_name = fields.Char(required=True)
    timeout_seconds = fields.Integer(required=True, default=60)
    maximum_tokens = fields.Integer(required=True, default=1200)
    temperature = fields.Float(required=True, default=0.1)
    active = fields.Boolean(default=True)
    api_key_reference = fields.Char(help="Credential reference only: env:VARIABLE or config:mogen_sop_ai.parameter_name.")
    test_status = fields.Selection([("not_tested", "Not Tested"), ("success", "Success"), ("failed", "Failed")], default="not_tested", readonly=True)
    last_test_date = fields.Datetime(readonly=True)

    _sql_constraints = [("sop_ai_provider_company_name_unique", "unique(company_id, name)", "Provider names must be unique per company.")]

    @api.constrains("timeout_seconds", "maximum_tokens", "temperature", "api_key_reference")
    def _check_provider_configuration(self):
        for provider in self:
            if provider.timeout_seconds < 1 or provider.maximum_tokens < 1:
                raise ValidationError(_("Timeout and maximum tokens must be positive."))
            if not 0.0 <= provider.temperature <= 2.0:
                raise ValidationError(_("Temperature must be between zero and two."))
            if provider.api_key_reference and not REFERENCE_PATTERN.match(provider.api_key_reference):
                raise ValidationError(_("API credential references must use env:NAME or config:mogen_sop_ai.parameter."))

    def _resolve_api_key(self):
        self.ensure_one()
        reference = self.api_key_reference
        if not reference:
            return False
        if reference.startswith("env:"):
            return os.environ.get(reference[4:])
        return self.env["ir.config_parameter"].sudo().get_param(reference[7:])


class MogenSopAiPromptTemplate(models.Model):
    _name = "mogen.sop.ai.prompt.template"
    _description = "S&OP AI Prompt Template"
    _check_company_auto = True
    _order = "company_id, code, version desc"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    analysis_type = fields.Selection([("demand", "Demand"), ("supply", "Supply"), ("inventory", "Inventory"), ("production", "Production"), ("import", "Import"), ("installation", "Installation"), ("finance", "Finance"), ("risk", "Risk"), ("executive_summary", "Executive Summary"), ("root_cause", "Root Cause")], required=True)
    system_instruction = fields.Text(required=True)
    user_prompt_template = fields.Text(required=True)
    output_schema = fields.Text(required=True, default="{}")
    version = fields.Char(required=True, default="1.0")
    active = fields.Boolean(default=True)

    _sql_constraints = [("sop_ai_prompt_company_code_version_unique", "unique(company_id, code, version)", "Prompt template code and version must be unique per company.")]

    @api.constrains("output_schema")
    def _check_output_schema(self):
        for template in self:
            try:
                if not isinstance(json.loads(template.output_schema), dict):
                    raise ValueError()
            except (ValueError, json.JSONDecodeError) as error:
                raise ValidationError(_("Output schema must be a JSON object.")) from error

    def render_prompt(self, input_snapshot):
        self.ensure_one()
        return self.user_prompt_template.replace("{input_snapshot}", input_snapshot or "{}")


class MogenSopAiAnalysis(models.Model):
    _name = "mogen.sop.ai.analysis"
    _description = "S&OP AI Analysis"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("New"), tracking=True)
    sop_plan_id = fields.Many2one("mogen.sop.plan", check_company=True, index=True)
    version_id = fields.Many2one("mogen.sop.plan.version", index=True)
    scenario_plan_id = fields.Many2one("mogen.sop.scenario", check_company=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    analysis_type = fields.Selection([("demand", "Demand"), ("supply", "Supply"), ("inventory", "Inventory"), ("production", "Production"), ("import", "Import"), ("installation", "Installation"), ("finance", "Finance"), ("risk", "Risk"), ("executive_summary", "Executive Summary"), ("root_cause", "Root Cause")], required=True, index=True)
    input_snapshot = fields.Text(required=True, readonly=True)
    input_payload_hash = fields.Char(readonly=True, index=True)
    prompt_template_id = fields.Many2one("mogen.sop.ai.prompt.template", required=True, check_company=True, index=True)
    prompt_template_version = fields.Char(readonly=True)
    provider_id = fields.Many2one("mogen.sop.ai.provider", required=True, check_company=True, index=True)
    model_name = fields.Char(readonly=True)
    response_text = fields.Text(readonly=True)
    structured_response = fields.Text(readonly=True)
    confidence = fields.Float(readonly=True)
    state = fields.Selection([("draft", "Draft"), ("queued", "Queued"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed"), ("reviewed", "Reviewed")], required=True, default="draft", index=True, tracking=True)
    requested_by_id = fields.Many2one("res.users", required=True, readonly=True, default=lambda self: self.env.user)
    reviewed_by_id = fields.Many2one("res.users", readonly=True, check_company=True)
    token_usage = fields.Integer(readonly=True)
    estimated_cost = fields.Monetary(currency_field="currency_id", readonly=True)
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    error_message = fields.Text(readonly=True)
    validation_errors = fields.Text(readonly=True)
    retry_count = fields.Integer(default=0, readonly=True)
    max_retries = fields.Integer(default=3, required=True)
    next_attempt_at = fields.Datetime(readonly=True, index=True)
    calculation_log = fields.Text(readonly=True)
    recommendation_ids = fields.One2many("mogen.sop.ai.recommendation", "ai_analysis_id", readonly=True)
    conversation_id = fields.Many2one("mogen.sop.ai.conversation", readonly=True, ondelete="set null", check_company=True, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    @api.constrains("max_retries")
    def _check_max_retries(self):
        if any(analysis.max_retries < 0 for analysis in self):
            raise ValidationError(_("Maximum retries cannot be negative."))

    def _check_requester_access(self):
        for analysis in self:
            for record in (analysis.sop_plan_id, analysis.scenario_plan_id):
                if record:
                    user_record = record.with_user(analysis.requested_by_id.id)
                    user_record.check_access_rights("read")
                    user_record.check_access_rule("read")

    def action_queue(self):
        for analysis in self:
            if analysis.state not in ("draft", "failed"):
                raise UserError(_("Only draft or failed AI analyses can be queued."))
            if not analysis.provider_id.active or not analysis.prompt_template_id.active:
                raise UserError(_("The selected provider and prompt template must be active."))
            analysis._check_requester_access()
            snapshot = analysis.input_snapshot.encode("utf-8")
            analysis.write({"state": "queued", "input_payload_hash": hashlib.sha256(snapshot).hexdigest(), "prompt_template_version": analysis.prompt_template_id.version, "model_name": analysis.provider_id.model_name, "error_message": False, "validation_errors": False, "next_attempt_at": fields.Datetime.now()})
        return True

    def _retry_or_fail(self, error):
        self.ensure_one()
        if self.retry_count < self.max_retries:
            delay = min(60 * (2 ** self.retry_count), 3600)
            self.write({"state": "queued", "retry_count": self.retry_count + 1, "next_attempt_at": fields.Datetime.now() + timedelta(seconds=delay), "error_message": str(error), "calculation_log": _("Gateway failure; retry %(attempt)s of %(total)s scheduled after %(delay)s seconds.", attempt=self.retry_count + 1, total=self.max_retries, delay=delay)})
        else:
            self.write({"state": "failed", "completed_at": fields.Datetime.now(), "error_message": str(error), "calculation_log": _("Gateway retries exhausted." )})

    def _process_in_background(self):
        """Called only by cron/background workers; never from a normal UI action."""
        for analysis in self:
            if analysis.state != "queued":
                continue
            analysis.write({"state": "running", "started_at": fields.Datetime.now(), "error_message": False})
            try:
                template = analysis.prompt_template_id
                response = GatewayClient(analysis.provider_id).invoke(analysis, template.system_instruction, template.render_prompt(analysis.input_snapshot), template.output_schema)
                raw_response, recommendations = StructuredResponseValidator(analysis).validate(response)
                analysis.recommendation_ids.unlink()
                analysis._create_recommendations(recommendations)
                usage = raw_response.get("token_usage", 0)
                cost = raw_response.get("estimated_cost", 0.0)
                analysis.write({"state": "completed", "completed_at": fields.Datetime.now(), "response_text": json.dumps(raw_response, sort_keys=True), "structured_response": json.dumps(raw_response, sort_keys=True), "confidence": float(raw_response.get("confidence", 0.0) or 0.0), "token_usage": int(usage or 0), "estimated_cost": max(float(cost or 0.0), 0.0), "calculation_log": _("Structured response validated; %(count)s draft recommendations created.", count=len(recommendations))})
                analysis._append_conversation_message(raw_response)
            except GatewayError as error:
                analysis._retry_or_fail(error)
            except (ValidationError, AccessError, ValueError, TypeError) as error:
                analysis.write({"state": "failed", "completed_at": fields.Datetime.now(), "validation_errors": str(error), "error_message": str(error), "calculation_log": _("AI output rejected by structured validation.")})
            except Exception as error:
                analysis._retry_or_fail(error)
        return True

    def _append_conversation_message(self, response):
        if not self.conversation_id:
            return
        try:
            snapshot = json.loads(self.input_snapshot)
            sources = snapshot.get("context", {}).get("source_links", [])
        except (TypeError, ValueError):
            sources = []
        self.env["mogen.sop.ai.message"].sudo().create({"conversation_id": self.conversation_id.id, "role": "assistant", "content": response.get("summary") or response.get("message") or _("Analysis completed. Review the evidence and draft recommendations."), "structured_content": json.dumps(response, sort_keys=True), "source_links": json.dumps(sources), "token_usage": int(response.get("token_usage", 0) or 0)})

    def _create_recommendations(self, recommendations):
        Recommendation = self.env["mogen.sop.ai.recommendation"]
        values = []
        for item in recommendations:
            values.append({"name": item["title"], "ai_analysis_id": self.id, "sop_plan_id": self.sop_plan_id.id, "scenario_plan_id": self.scenario_plan_id.id, "company_id": self.company_id.id, "recommendation_type": item["action"], "priority": item["priority"] if item["priority"] in ("low", "normal", "high", "critical") else "normal", "title": item["title"], "description": item["description"], "reason": item["reason"], "expected_impact": item["expected_impact"], "confidence": self.confidence, "source_reference_ids": json.dumps(item["source_references"], sort_keys=True), "proposed_action": item["action"], "state": "proposed", "product_id": item["product_id"], "warehouse_id": item["warehouse_id"], "quantity": item["quantity"], "required_date": item["required_date"], "core_recommendation_type": item["recommendation_type"]})
        if values:
            Recommendation.create(values)

    @api.model
    def cron_process_queued_analyses(self):
        analyses = self.search([("state", "=", "queued"), "|", ("next_attempt_at", "=", False), ("next_attempt_at", "<=", fields.Datetime.now())], order="next_attempt_at, id", limit=20)
        for analysis in analyses:
            try:
                analysis.sudo()._process_in_background()
            except Exception:
                self.env.cr.rollback()
        return True


class MogenSopAiRecommendation(models.Model):
    _name = "mogen.sop.ai.recommendation"
    _description = "S&OP AI Recommendation"
    _order = "priority desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True)
    ai_analysis_id = fields.Many2one("mogen.sop.ai.analysis", required=True, ondelete="cascade", check_company=True, index=True)
    sop_plan_id = fields.Many2one("mogen.sop.plan", check_company=True, index=True)
    scenario_plan_id = fields.Many2one("mogen.sop.scenario", check_company=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    recommendation_type = fields.Selection([(action, action.replace("_", " ").title()) for action in sorted(ALLOWED_ACTIONS)], required=True)
    priority = fields.Selection([("low", "Low"), ("normal", "Normal"), ("high", "High"), ("critical", "Critical")], required=True, default="normal", index=True)
    title = fields.Char(required=True)
    description = fields.Text()
    reason = fields.Text()
    expected_impact = fields.Text()
    confidence = fields.Float()
    source_reference_ids = fields.Text(readonly=True)
    proposed_action = fields.Char(required=True, readonly=True)
    state = fields.Selection([("proposed", "Proposed"), ("reviewed", "Reviewed"), ("approved", "Approved"), ("rejected", "Rejected"), ("converted", "Converted")], required=True, default="proposed", index=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True, check_company=True)
    recommendation_id = fields.Many2one("mogen.sop.recommendation", readonly=True, check_company=True)
    product_id = fields.Many2one("product.product", index=True)
    warehouse_id = fields.Many2one("stock.warehouse", check_company=True, index=True)
    quantity = fields.Float()
    required_date = fields.Date()
    core_recommendation_type = fields.Selection([("purchase", "Purchase"), ("manufacture", "Manufacture"), ("transfer", "Transfer"), ("forecast_adjustment", "Forecast Adjustment"), ("warning", "Warning")], required=True, readonly=True)

    @api.constrains("quantity")
    def _check_quantity(self):
        if any(recommendation.quantity < 0 for recommendation in self):
            raise ValidationError(_("Recommendation quantity cannot be negative."))

    def _require_ai_manager(self):
        if not self.env.user.has_group("mogen_sop_ai.group_sop_ai_manager"):
            raise AccessError(_("Only an S&OP AI manager can review AI recommendations."))

    def action_approve(self):
        self._require_ai_manager()
        if any(recommendation.state not in ("proposed", "reviewed") for recommendation in self):
            raise UserError(_("Only proposed or reviewed recommendations can be approved."))
        self.write({"state": "approved", "reviewed_by_id": self.env.user.id})
        return True

    def action_reject(self):
        self._require_ai_manager()
        self.filtered(lambda recommendation: recommendation.state in ("proposed", "reviewed")).write({"state": "rejected", "reviewed_by_id": self.env.user.id})
        return True

    def action_convert_to_sop_recommendation(self):
        self._require_ai_manager()
        for recommendation in self:
            if recommendation.state != "approved":
                raise UserError(_("An AI recommendation must be approved before conversion."))
            if not recommendation.sop_plan_id:
                raise UserError(_("An S&OP plan is required to create a draft recommendation."))
            core = self.env["mogen.sop.recommendation"].create({"name": recommendation.title, "plan_id": recommendation.sop_plan_id.id, "recommendation_type": recommendation.core_recommendation_type, "product_id": recommendation.product_id.id, "warehouse_id": recommendation.warehouse_id.id, "quantity": recommendation.quantity, "required_date": recommendation.required_date, "priority": {"low": "0", "normal": "1", "high": "2", "critical": "3"}[recommendation.priority], "reason": recommendation.reason, "impact": recommendation.expected_impact, "source_model": self._name, "source_res_id": recommendation.id})
            recommendation.write({"state": "converted", "recommendation_id": core.id})
        return True
