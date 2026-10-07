from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpPeriodCostReverseWizard(models.TransientModel):
    _name = 'mrp.period.cost.reverse.wizard'
    _description = 'Reverse Posted Period Cost'

    period_id = fields.Many2one('mrp.period.cost', required=True, readonly=True)
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.ensure_one()
        return self.period_id.action_reverse_to_draft(self.reason)


class MrpPeriodCostPostWizard(models.TransientModel):
    _name = 'mrp.period.cost.post.wizard'
    _description = 'Confirm Posting of Period Cost'

    period_id = fields.Many2one('mrp.period.cost', required=True, readonly=True)
    date_from = fields.Date(related='period_id.date_from')
    date_to = fields.Date(related='period_id.date_to')
    adjustment_date = fields.Date(related='period_id.adjustment_date')
    allocation_base = fields.Selection(related='period_id.allocation_base')
    line_count = fields.Integer(compute='_compute_summary')
    total_variance = fields.Float(compute='_compute_summary', digits='Product Price')
    total_inventory = fields.Float(compute='_compute_summary', digits='Product Price')
    total_expense = fields.Float(compute='_compute_summary', digits='Product Price')
    sold_line_count = fields.Integer(compute='_compute_summary')
    warning_text = fields.Text(compute='_compute_summary')
    confirm_checked = fields.Boolean(string='I have checked and understand')

    @api.depends('period_id')
    def _compute_summary(self):
        for wiz in self:
            lines = wiz.period_id.line_ids
            period = wiz.period_id
            wiz.line_count = len(lines)
            wiz.total_variance = period.diff_dl + period.diff_idl + period.diff_oh
            wiz.total_inventory = sum(lines.mapped('allocated_inventory_total'))
            wiz.total_expense = sum(lines.mapped('allocated_period_expense'))
            wiz.sold_line_count = len(lines.filtered(
                lambda l: l.qty_on_hand < l.quantity_produced))
            warnings = []
            lock_warning = period._lock_date_warning()
            if lock_warning:
                warnings.append(lock_warning)
            if not wiz.total_inventory:
                warnings.append(_("No variance will be added to inventory: all produced stock has been sold or issued, or the variance is zero."))
            if wiz.sold_line_count:
                warnings.append(_("%s MO(s) have already been partly or fully sold. Only stock still held (including stock transferred between warehouses) receives the variance; the sold share is report-only and not posted.", wiz.sold_line_count))
            wiz.warning_text = '\n'.join('- %s' % w for w in warnings)

    def action_confirm(self):
        self.ensure_one()
        if not self.confirm_checked:
            raise UserError(_("Please tick the confirmation box before posting."))
        return self.period_id.action_post()
