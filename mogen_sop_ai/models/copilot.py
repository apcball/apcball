"""Persisted, asynchronous Smart S&OP Copilot conversations."""
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class MogenSopAiConversation(models.Model):
    _name = "mogen.sop.ai.conversation"
    _description = "S&OP AI Conversation"
    _order = "write_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("New conversation"))
    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    sop_plan_id = fields.Many2one("mogen.sop.plan", check_company=True, index=True)
    scenario_plan_id = fields.Many2one("mogen.sop.scenario", check_company=True, index=True)
    active = fields.Boolean(default=True)
    message_ids = fields.One2many("mogen.sop.ai.message", "conversation_id")

    def _check_owner(self):
        if any(record.user_id != self.env.user and not self.env.user.has_group("mogen_sop_ai.group_sop_ai_manager") for record in self):
            raise AccessError(_("You can only manage your own AI conversations."))

    def action_clear(self):
        self._check_owner()
        self.unlink()
        return True


class MogenSopAiMessage(models.Model):
    _name = "mogen.sop.ai.message"
    _description = "S&OP AI Conversation Message"
    _order = "created_at, id"
    _check_company_auto = True

    conversation_id = fields.Many2one("mogen.sop.ai.conversation", required=True, ondelete="cascade", check_company=True, index=True)
    company_id = fields.Many2one(related="conversation_id.company_id", store=True, readonly=True, index=True)
    role = fields.Selection([("user", "User"), ("assistant", "Assistant"), ("system", "System"), ("tool", "Tool")], required=True)
    content = fields.Text(required=True)
    structured_content = fields.Text(readonly=True)
    created_at = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True, index=True)
    token_usage = fields.Integer(readonly=True)
    source_links = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)


class MogenSopAiCopilotService(models.AbstractModel):
    _name = "mogen.sop.ai.copilot.service"
    _description = "Smart S&OP Copilot Service"

    def _provider_and_template(self, company):
        provider = self.env["mogen.sop.ai.provider"].search([("company_id", "=", company.id), ("active", "=", True)], limit=1)
        template = self.env["mogen.sop.ai.prompt.template"].search([("company_id", "=", company.id), ("analysis_type", "=", "executive_summary"), ("active", "=", True)], limit=1)
        if not provider or not template:
            raise UserError(_("Configure an active AI provider and Executive Summary prompt template first."))
        return provider, template

    def ask(self, question, conversation_id=False, plan_id=False, scenario_id=False, filters=None):
        if not isinstance(question, str) or not question.strip():
            raise UserError(_("Enter a Copilot question."))
        conversation = self.env["mogen.sop.ai.conversation"].browse(conversation_id).exists() if conversation_id else False
        if conversation:
            conversation._check_owner()
        else:
            conversation = self.env["mogen.sop.ai.conversation"].create({"name": question[:80], "sop_plan_id": plan_id or False, "scenario_plan_id": scenario_id or False})
        context = self.env["mogen.sop.dashboard.service"].get_active_context(plan_id or conversation.sop_plan_id.id, scenario_id or conversation.scenario_plan_id.id, filters or {}, limit=50)
        payload = {"question": question.strip(), "context": context}
        if len(json.dumps(payload, default=str)) > 50000:
            payload["context"]["alerts"] = payload["context"]["alerts"][:20]
            payload["context"]["recommendations"] = payload["context"]["recommendations"][:20]
        self.env["mogen.sop.ai.message"].create({"conversation_id": conversation.id, "role": "user", "content": question.strip(), "structured_content": json.dumps({"filters": filters or {}}), "source_links": json.dumps(context["source_links"])})
        provider, template = self._provider_and_template(conversation.company_id)
        analysis = self.env["mogen.sop.ai.analysis"].create({"name": _("Copilot: %(question)s", question=question[:60]), "sop_plan_id": conversation.sop_plan_id.id, "scenario_plan_id": conversation.scenario_plan_id.id, "company_id": conversation.company_id.id, "analysis_type": "executive_summary", "input_snapshot": json.dumps(payload, default=str, sort_keys=True), "prompt_template_id": template.id, "provider_id": provider.id, "conversation_id": conversation.id})
        analysis.action_queue()
        return {"conversation_id": conversation.id, "analysis_id": analysis.id, "state": analysis.state}

    def get_conversation(self, conversation_id):
        conversation = self.env["mogen.sop.ai.conversation"].browse(conversation_id).exists()
        if not conversation:
            return {"messages": []}
        conversation._check_owner()
        return {"id": conversation.id, "name": conversation.name, "messages": [{"id": message.id, "role": message.role, "content": message.content, "sources": json.loads(message.source_links or "[]"), "error": message.error_message} for message in conversation.message_ids]}
