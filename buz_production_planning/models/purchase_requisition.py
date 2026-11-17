# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from odoo import _, fields, models


class PurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition'

    buz_plan_run_id = fields.Many2one(
        'buz.plan.run', string="Production Plan", index=True, readonly=True, copy=False,
        ondelete='set null',
        help="The production plan whose Buy suggestions created this blanket order.")

    def action_open_buz_plan(self):
        self.ensure_one()
        if not self.buz_plan_run_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _("Production Plan"),
            'res_model': 'buz.plan.run', 'res_id': self.buz_plan_run_id.id, 'view_mode': 'form',
        }
