import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import UserError


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

    def _format_engine_log(self, result):
        out = [
            'valuation_delta: %s' % result.get('valuation_delta', 0.0),
            'qty_delta: %s' % result.get('qty_delta', 0.0),
            'cogs_delta: %s' % result.get('cogs_delta', 0.0),
            'backup_id: %s' % result.get('backup_id', False),
            '',
        ]
        for g in result.get('groups', []):
            out.append(
                'product=%s warehouse=%s state=%s baseline=%s value_delta=%s '
                'qty_delta=%s quant_delta=%s note=%s' % (
                    g.get('product_id'), g.get('warehouse_id'), g.get('state'),
                    g.get('baseline'), g.get('value_delta', 0.0),
                    g.get('qty_delta', 0.0), g.get('quant_delta', 0.0),
                    g.get('note', '')))
        return '\n'.join(out)

    def _write_engine_result(self, result, log_field):
        """Persist a run() result onto this document and its lines. Called
        OUTSIDE engine.run() so it survives a dry-run rollback."""
        self.ensure_one()
        applied = log_field == 'apply_log'
        gmap = {(g['product_id'], g['warehouse_id']): g
                for g in result.get('groups', [])}
        for line in self.line_ids:
            g = gmap.get((line.product_id.id, line.warehouse_id.id))
            if not g:
                continue
            q0, v0 = g.get('baseline', (0.0, 0.0))
            gstate = g.get('state', 'previewed')
            if gstate == 'previewed' and applied:
                gstate = 'applied'
            line.write({
                'baseline_qty': q0, 'baseline_value': v0,
                'delta_qty': g.get('qty_delta', 0.0),
                'delta_value': g.get('value_delta', 0.0),
                'state': gstate,
                'result_note': g.get('note', ''),
            })
        self.mismatch_ids.unlink()
        mvals = []
        for g in result.get('groups', []):
            for m in g.get('mismatches', []):
                mvals.append(dict(m, adjustment_id=self.id))
        if mvals:
            self.env['stock.count.adjustment.mismatch'].create(mvals)
        self.write({
            log_field: self._format_engine_log(result),
            'valuation_delta': result.get('valuation_delta', 0.0),
            'qty_delta': result.get('qty_delta', 0.0),
            'cogs_delta': result.get('cogs_delta', 0.0),
        })

    def action_preview(self):
        self.ensure_one()
        result = self.env['count.adjust.engine'].run(self, dry_run=True)
        self._write_engine_result(result, 'preview_log')
        self.write({'state': 'previewed', 'line_hash': self._line_hash()})
        return True

    def action_apply(self):
        self.ensure_one()
        if self.state != 'previewed':
            raise UserError(_('Preview the adjustment before applying it.'))
        if self._line_hash() != self.line_hash:
            raise UserError(_('Lines changed since preview. Run Preview again.'))
        result = self.env['count.adjust.engine'].run(self, dry_run=False)
        self._write_engine_result(result, 'apply_log')
        vals = {'state': 'applied'}
        if result.get('backup_id'):
            vals['backup_id'] = result['backup_id']
        self.write(vals)
        return True

    def action_rollback(self):
        self.ensure_one()
        if not self.backup_id:
            raise UserError(_('This adjustment has no backup to roll back.'))
        self.backup_id.action_restore()
        self.state = 'rolled_back'

    def action_import(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Lines can only be imported into a draft adjustment.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Adjustment Lines'),
            'res_model': 'stock.count.adjustment.import',
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context, default_adjustment_id=self.id),
        }
