from odoo import fields, models


class MrpPeriodCostReverseWizard(models.TransientModel):
    _name = 'mrp.period.cost.reverse.wizard'
    _description = 'Reverse Posted Period Cost'

    period_id = fields.Many2one('mrp.period.cost', required=True, readonly=True)
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.ensure_one()
        return self.period_id.action_reverse_to_draft(self.reason)
