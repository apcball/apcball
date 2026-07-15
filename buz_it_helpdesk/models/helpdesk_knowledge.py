from odoo import fields, models


class HelpdeskKnowledgeArticle(models.Model):
    _name = "it.helpdesk.knowledge.article"
    _description = "Helpdesk Knowledge Article"
    _check_company_auto = True
    _order = "write_date desc, name"

    name = fields.Char(string="Article Title", required=True)
    content = fields.Html(required=True)
    category_id = fields.Many2one("it.helpdesk.category", ondelete="set null", check_company=True)
    tag_ids = fields.Many2many("it.helpdesk.tag", string="Tags")
    state = fields.Selection([("draft", "Unpublished"), ("published", "Published")], default="draft", required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    published_date = fields.Datetime(readonly=True)
    def action_create_ticket(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Create Ticket", "res_model": "it.helpdesk.ticket", "view_mode": "form", "target": "current", "context": {"default_subject": self.name, "default_description": self.content, "default_category_id": self.category_id.id}}

    def action_publish(self):
        self.write({"state": "published", "published_date": fields.Datetime.now()})

    def action_unpublish(self):
        self.write({"state": "draft", "published_date": False})
