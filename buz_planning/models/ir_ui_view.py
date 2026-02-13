from odoo import fields, models

MOG_GANTT_VIEW = ("mog_gantt", "Gantt")


class IrUIView(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(selection_add=[MOG_GANTT_VIEW])

    def _is_qweb_based_view(self, view_type):
        return view_type == MOG_GANTT_VIEW[0] or super()._is_qweb_based_view(
            view_type
        )
