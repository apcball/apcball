from odoo import fields, models, tools


class HelpdeskTicketReport(models.Model):
    _name = "it.helpdesk.ticket.report"
    _description = "Helpdesk Ticket Analysis"
    _auto = False
    _rec_name = "ticket_id"

    ticket_id = fields.Many2one("it.helpdesk.ticket", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    team_id = fields.Many2one("it.helpdesk.team", readonly=True)
    category_id = fields.Many2one("it.helpdesk.category", readonly=True)
    department = fields.Char(readonly=True)
    assigned_to = fields.Many2one("res.users", readonly=True)
    priority_id = fields.Many2one("it.helpdesk.priority", readonly=True)
    stage_id = fields.Many2one("it.helpdesk.stage", readonly=True)
    create_date = fields.Datetime(readonly=True)
    first_response_hours = fields.Float(readonly=True)
    resolution_hours_elapsed = fields.Float(readonly=True)
    sla_compliant = fields.Boolean(readonly=True)
    is_overdue = fields.Boolean(readonly=True)
    ticket_count = fields.Integer(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW it_helpdesk_ticket_report AS (
                SELECT t.id, t.id AS ticket_id, t.company_id, t.team_id,
                    t.category_id, t.department, t.assigned_to, t.priority_id,
                    t.stage_id, t.create_date, t.first_response_hours,
                    t.resolution_hours_elapsed, t.sla_compliant,
                    CASE WHEN t.sla_deadline IS NOT NULL
                        AND t.sla_deadline < NOW() AND NOT COALESCE(s.is_closed, FALSE)
                        THEN TRUE ELSE FALSE END AS is_overdue,
                    1 AS ticket_count
                FROM it_helpdesk_ticket t
                LEFT JOIN it_helpdesk_stage s ON s.id = t.stage_id
            )
        """)
