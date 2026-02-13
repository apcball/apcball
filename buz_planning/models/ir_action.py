from odoo import fields, models

from .ir_ui_view import MOG_GANTT_VIEW


class ActWindowView(models.Model):
    _inherit = "ir.actions.act_window.view"

    view_mode = fields.Selection(
        selection_add=[MOG_GANTT_VIEW], ondelete={"mog_gantt": "cascade"}
    )
