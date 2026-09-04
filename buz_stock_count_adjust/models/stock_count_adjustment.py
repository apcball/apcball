import hashlib

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

    def write(self, vals):
        res = super().write(vals)
        if 'line_ids' in vals:
            self._reset_hash_if_changed()
        return res

    def _reset_hash_if_changed(self):
        for doc in self:
            if doc.line_hash and doc._line_hash() != doc.line_hash:
                # plain field assignment, NOT a nested write() — avoids
                # re-entering this override
                doc.state = 'draft'
                doc.line_hash = False

    def _line_hash(self):
        self.ensure_one()
        payload = sorted(
            (l.product_id.id, l.warehouse_id.id, l.bucket_seq,
             round(l.target_qty, 6), round(l.target_value, 6))
            for l in self.line_ids)
        return hashlib.sha256(repr(payload).encode()).hexdigest()

    def _line_groups(self):
        self.ensure_one()
        groups = {}
        for line in self.line_ids.sorted(lambda l: (l.bucket_seq, l.id)):
            groups.setdefault(
                (line.product_id.id, line.warehouse_id.id),
                self.env['stock.count.adjustment.line'])
            groups[(line.product_id.id, line.warehouse_id.id)] |= line
        return list(groups.values())

    def action_preview(self):
        raise NotImplementedError

    def action_apply(self):
        raise NotImplementedError

    def action_rollback(self):
        raise NotImplementedError

    def action_import(self):
        raise NotImplementedError
