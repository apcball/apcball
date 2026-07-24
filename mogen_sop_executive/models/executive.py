"""Cached, permission-aware executive decision-support endpoints."""
import json
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MogenSopExecutiveSummaryCache(models.Model):
    _name = "mogen.sop.executive.summary.cache"
    _description = "S&OP Executive Summary Cache"
    _order = "generated_at desc, id desc"
    _check_company_auto = True

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    sop_plan_id = fields.Many2one("mogen.sop.plan", check_company=True, index=True)
    scenario_id = fields.Many2one("mogen.sop.scenario", check_company=True, index=True)
    analysis_id = fields.Many2one("mogen.sop.ai.analysis", readonly=True, ondelete="set null", check_company=True)
    state = fields.Selection([("draft", "Draft"), ("queued", "Queued"), ("completed", "Completed"), ("failed", "Failed")], default="draft", required=True, index=True)
    summary_text = fields.Text(readonly=True)
    snapshot_date = fields.Datetime(readonly=True)
    provider_name = fields.Char(readonly=True)
    model_name = fields.Char(readonly=True)
    generated_at = fields.Datetime(readonly=True)
    scheduled_refresh = fields.Boolean(default=False)

    @api.model
    def cron_refresh_summary_cache(self):
        caches = self.search([("state", "in", ("queued", "draft"))] + (["|", ("scheduled_refresh", "=", True), ("state", "=", "queued")] if True else []), limit=20)
        for cache in caches:
            analysis = cache.analysis_id
            if not analysis:
                continue
            if analysis.state == "completed":
                try:
                    payload = json.loads(analysis.structured_response or "{}")
                except ValueError:
                    payload = {}
                cache.write({"state": "completed", "summary_text": payload.get("summary") or analysis.response_text, "snapshot_date": analysis.completed_at, "provider_name": analysis.provider_id.name, "model_name": analysis.model_name, "generated_at": analysis.completed_at})
            elif analysis.state == "failed":
                cache.write({"state": "failed"})
        return True


class MogenSopExecutiveService(models.AbstractModel):
    _name = "mogen.sop.executive.service"
    _description = "S&OP Executive Decision Service"

    def _dashboard_context(self, plan_id=False, scenario_id=False, filters=None):
        return self.env["mogen.sop.dashboard.service"].get_active_context(plan_id, scenario_id, filters or {}, 100)

    def get_executive_kpis(self, plan_id=False, scenario_id=False, filters=None):
        context = self._dashboard_context(plan_id, scenario_id, filters)
        forecast = self.env.registry.models.get("mogen.sop.forecast.result")
        accuracy = 0.0
        if forecast and plan_id:
            rows = self.env["mogen.sop.forecast.result"].read_group([("sop_plan_id", "=", plan_id), ("is_valid", "=", True)], ["forecast_qty:sum"], [])
            accuracy = rows[0].get("forecast_qty", 0.0) if rows else 0.0
        return {"snapshot_date": context["snapshot_date"], "kpis": [{"name": "Open Alerts", "value": len(context["alerts"])}, {"name": "Pending Decisions", "value": len(context["recommendations"])}, {"name": "Forecast Volume", "value": accuracy}, {"name": "Composite Risk Score", "value": 0.0}]}

    def get_decision_queue(self, plan_id=False, scenario_id=False, filters=None):
        context = self._dashboard_context(plan_id, scenario_id, filters)
        items = [{"type": "alert", "id": row["id"], "title": row["name"], "priority": row["severity"]} for row in context["alerts"]]
        items += [{"type": "recommendation", "id": row["id"], "title": row["name"], "priority": row["priority"]} for row in context["recommendations"]]
        ai_model = self.env.registry.models.get("mogen.sop.ai.recommendation")
        if ai_model:
            domain = [("state", "=", "proposed")]
            if plan_id: domain.append(("sop_plan_id", "=", plan_id))
            items += [{"type": "ai", "id": row.id, "title": row.title, "priority": row.priority} for row in self.env["mogen.sop.ai.recommendation"].search(domain, limit=50)]
        return {"snapshot_date": context["snapshot_date"], "items": items[:100]}

    def get_scenario_comparison(self, plan_id=False, scenario_ids=None):
        scenario_ids = scenario_ids or []
        scenarios = self.env["mogen.sop.scenario"].browse(scenario_ids).exists()
        scenarios.check_access_rights("read"); scenarios.check_access_rule("read")
        return {"snapshot_date": self.env.cr.now(), "rows": [{"id": row.id, "name": row.name, "sales": 0.0, "revenue": 0.0, "cost": 0.0, "gross_profit": 0.0, "cash_requirement": 0.0, "inventory_value": 0.0, "service_level": 0.0, "stockout_count": 0, "risk_score": 0.0} for row in scenarios]}

    def get_risk_heatmap(self, plan_id=False, scenario_id=False, filters=None):
        return {"snapshot_date": self.env.cr.now(), "cells": [], "message": _("Risk data will appear when the Phase 3 risk assessment model is installed.")}

    def get_forecast_performance(self, plan_id=False, filters=None):
        if not self.env.registry.models.get("mogen.sop.forecast.result"):
            return {"snapshot_date": self.env.cr.now(), "rows": []}
        domain = [("is_valid", "=", True)] + ([("sop_plan_id", "=", plan_id)] if plan_id else [])
        rows = self.env["mogen.sop.forecast.result"].read_group(domain, ["forecast_qty:sum"], ["model_id"], lazy=False)
        return {"snapshot_date": self.env.cr.now(), "rows": [{"model": row.get("model_id") and row["model_id"][1], "forecast_qty": row.get("forecast_qty", 0.0)} for row in rows]}

    def get_operational_readiness(self, plan_id=False, filters=None):
        context = self._dashboard_context(plan_id, False, filters)
        return {"snapshot_date": context["snapshot_date"], "items": [{"name": "Open operational alerts", "value": len(context["alerts"])}]}

    def request_ai_executive_summary(self, plan_id=False, scenario_id=False, filters=None):
        context = self._dashboard_context(plan_id, scenario_id, filters)
        company = self.env.company
        provider = self.env["mogen.sop.ai.provider"].search([("company_id", "=", company.id), ("active", "=", True)], limit=1)
        template = self.env["mogen.sop.ai.prompt.template"].search([("company_id", "=", company.id), ("analysis_type", "=", "executive_summary"), ("active", "=", True)], limit=1)
        if not provider or not template:
            raise UserError(_("Configure an active AI provider and Executive Summary prompt template first."))
        cache = self.env["mogen.sop.executive.summary.cache"].create({"company_id": company.id, "sop_plan_id": plan_id or False, "scenario_id": scenario_id or False, "state": "queued"})
        analysis = self.env["mogen.sop.ai.analysis"].create({"name": _("Executive summary"), "company_id": company.id, "sop_plan_id": plan_id or False, "scenario_plan_id": scenario_id or False, "analysis_type": "executive_summary", "input_snapshot": json.dumps({"executive_context": context}, default=str, sort_keys=True), "prompt_template_id": template.id, "provider_id": provider.id})
        analysis.action_queue(); cache.write({"analysis_id": analysis.id})
        return {"cache_id": cache.id, "state": "queued"}

    def get_ai_executive_summary(self, plan_id=False, scenario_id=False):
        domain = [("company_id", "=", self.env.company.id)] + ([("sop_plan_id", "=", plan_id)] if plan_id else []) + ([("scenario_id", "=", scenario_id)] if scenario_id else [])
        cache = self.env["mogen.sop.executive.summary.cache"].search(domain, order="generated_at desc, id desc", limit=1)
        return {"summary": cache.summary_text if cache and cache.state == "completed" else False, "state": cache.state if cache else "missing", "snapshot_date": cache.snapshot_date if cache else False, "provider": cache.provider_name if cache else False, "model": cache.model_name if cache else False, "generated_at": cache.generated_at if cache else False}
