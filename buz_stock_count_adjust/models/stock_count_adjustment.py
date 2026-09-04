from odoo import api, fields, models


class StockCountAdjustment(models.Model):
    _name = 'stock.count.adjustment'
    _description = 'Stock Count Adjustment'
    _order = 'id desc'

    name = fields.Char(default='/', copy=False, readonly=True, index=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    cutoff_date = fields.Date(
        required=True, help="The physical count date. FIFO is rebuilt as of end of this day (Asia/Bangkok).")
    state = fields.Selection(
        [('draft', 'Draft'),
         ('previewed', 'Previewed'),
         ('applied', 'Applied'),
         ('rolled_back', 'Rolled Back')],
        default='draft', required=True, copy=False, index=True)

    line_ids = fields.One2many(
        'stock.count.adjustment.line', 'adjustment_id', string='Lines', copy=True)
    mismatch_ids = fields.One2many(
        'stock.count.adjustment.mismatch', 'adjustment_id', string='Mismatches')
    backup_id = fields.Many2one(
        'stock.count.adjustment.backup', string='Backup', copy=False, readonly=True)

    preview_log = fields.Text(readonly=True, copy=False)
    apply_log = fields.Text(readonly=True, copy=False)
    line_hash = fields.Char(
        copy=False, readonly=True,
        help="Hash of the line set captured at preview; apply refuses if lines changed since.")

    valuation_delta = fields.Float(
        string='Valuation Delta', readonly=True, copy=False,
        digits='Product Price')
    cogs_delta = fields.Float(
        string='COGS Delta', readonly=True, copy=False, digits='Product Price')
    qty_delta = fields.Float(
        string='Qty Delta', readonly=True, copy=False,
        digits='Product Unit of Measure')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'stock.count.adjustment') or '/'
        return super().create(vals_list)

    def action_preview(self):
        raise NotImplementedError

    def action_apply(self):
        raise NotImplementedError

    def action_rollback(self):
        raise NotImplementedError

    def action_import(self):
        raise NotImplementedError
