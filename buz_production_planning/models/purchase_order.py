# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from odoo import _, api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    buz_plan_run_id = fields.Many2one(
        'buz.plan.run', string="Production Plan", compute='_compute_buz_plan_run_id',
        help="The production plan that asked for this purchase: through its blanket order, "
             "or directly when the plan created this RFQ.")

    @api.depends('requisition_id.buz_plan_run_id', 'order_line')
    def _compute_buz_plan_run_id(self):
        # Reverse side of buz.plan.suggestion.purchase_line_id, read in one query.
        by_order = {}
        pending = self.filtered(lambda po: po.id and not po.requisition_id.buz_plan_run_id)
        if pending:
            for sugg in self.env['buz.plan.suggestion'].search(
                    [('purchase_line_id.order_id', 'in', pending.ids)]):
                by_order.setdefault(sugg.purchase_line_id.order_id.id, sugg.run_id)
        for po in self:
            po.buz_plan_run_id = po.requisition_id.buz_plan_run_id or by_order.get(po.id, False)

    def action_open_buz_plan(self):
        self.ensure_one()
        if not self.buz_plan_run_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _("Production Plan"),
            'res_model': 'buz.plan.run', 'res_id': self.buz_plan_run_id.id, 'view_mode': 'form',
        }
