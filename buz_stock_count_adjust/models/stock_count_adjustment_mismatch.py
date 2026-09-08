from odoo import _, fields, models
from odoo.exceptions import UserError


class StockCountAdjustmentMismatch(models.Model):
    _name = 'stock.count.adjustment.mismatch'
    _description = 'Stock Count Adjustment Mismatch'
    _order = 'id'

    adjustment_id = fields.Many2one(
        'stock.count.adjustment', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='adjustment_id.company_id', store=True, index=True)
    product_id = fields.Many2one('product.product', index=True)
    warehouse_id = fields.Many2one('stock.warehouse', index=True)
    svl_id = fields.Many2one('stock.valuation.layer', string='Valuation Layer')
    move_id = fields.Many2one('stock.move', string='Stock Move')
    move_line_id = fields.Many2one(
        'stock.move.line', string='Suspect Move Line')

    svl_qty = fields.Float(digits='Product Unit of Measure')
    move_net_qty = fields.Float(digits='Product Unit of Measure')
    diff = fields.Float(digits='Product Unit of Measure')

    suggested_location_id = fields.Many2one(
        'stock.location', string='Suggested Location',
        help="Best guess (the pair's lot_stock_id). Shown, not auto-applied.")

    state = fields.Selection(
        [('open', 'Open'),
         ('fixed', 'Fixed'),
         ('ignored', 'Ignored')],
        default='open', required=True, copy=False)

    def action_ignore(self):
        for rec in self:
            if rec.state != 'open':
                raise UserError(_(
                    'Mismatch %s is already %s.') % (rec.id, rec.state))
            rec.state = 'ignored'
        return True

    def action_fix_move_line(self):
        """Manually correct the suspect move line's corrupted end and re-align
        the two affected stock.quant rows by `diff`. Runs post-apply, per human
        click -- so it writes its own one-row backup entries linked to the
        adjustment's backup (if any) before mutating, so action_restore catches
        this fix too.

        Move-line location write is raw SQL (Odoo 17 stock.move.line.write on a
        done line has quant-correcting side effects; the raw UPDATE keeps the
        explicit quant arithmetic below the only quant mutation, and matches
        action_restore's raw restore).
        """
        self.ensure_one()
        if self.state != 'open':
            raise UserError(_(
                'Mismatch %s is already %s.') % (self.id, self.state))
        if self.adjustment_id.state != 'applied' or (
                self.adjustment_id.backup_id
                and self.adjustment_id.backup_id.state != 'active'):
            raise UserError(_(
                'The parent adjustment must be applied and its backup active '
                'to fix a mismatch line.'))
        ml = self.move_line_id
        move = self.move_id
        suggested = self.suggested_location_id
        if not ml or not suggested:
            raise UserError(_(
                'Mismatch %s has no suspect move line or suggested location.'
            ) % self.id)

        if ml.location_id != move.location_id:
            field = 'location_id'
            old_loc = ml.location_id
        elif ml.location_dest_id != move.location_dest_id:
            field = 'location_dest_id'
            old_loc = ml.location_dest_id
        else:
            raise UserError(_(
                'Move line %s already agrees with its stock move header; '
                'nothing to fix.') % ml.id)

        cr = self.env.cr
        uid = self.env.uid
        diff = self.diff
        company = self.adjustment_id.company_id
        product = self.product_id
        Quant = self.env['stock.quant']
        ML = self.env['stock.move.line']
        Move = self.env['stock.move']
        backup = self.adjustment_id.backup_id

        def _quant(location):
            q = Quant.search([
                ('product_id', '=', product.id),
                ('location_id', '=', location.id),
                ('company_id', '=', company.id)], limit=1)
            if not q:
                q = Quant.with_context(
                    skip_warehouse_consistency_check=True).create({
                        'product_id': product.id,
                        'location_id': location.id,
                        'company_id': company.id,
                        'quantity': 0.0})
            return q

        to_quant = _quant(suggested)
        from_quant = _quant(old_loc)

        # --- self-contained rollback rows (pre-image), before any mutation ---
        if backup:
            ML.flush_model(['location_id', 'location_dest_id', 'date'])
            Move.flush_model(['date'])
            Quant.flush_model(['quantity'])
            cr.execute("""
                INSERT INTO stock_count_adjustment_backup_moveline
                    (backup_id, move_line_id, move_id, location_id,
                     location_dest_id, ml_date, move_date, was_generated,
                     create_uid, create_date, write_uid, write_date)
                SELECT %s, sml.id, sml.move_id, sml.location_id,
                       sml.location_dest_id, sml.date, sm.date, false,
                       %s, now() at time zone 'UTC', %s, now() at time zone 'UTC'
                FROM stock_move_line sml
                JOIN stock_move sm ON sm.id = sml.move_id
                WHERE sml.id = %s
            """, (backup.id, uid, uid, ml.id))
            for q in (to_quant, from_quant):
                cr.execute("""
                    INSERT INTO stock_count_adjustment_backup_quant
                        (backup_id, quant_id, quantity,
                         create_uid, create_date, write_uid, write_date)
                    VALUES (%s, %s, %s,
                            %s, now() at time zone 'UTC', %s,
                            now() at time zone 'UTC')
                """, (backup.id, q.id, q.quantity, uid, uid))
            backup.invalidate_recordset(
                ['moveline_line_ids', 'quant_line_ids'])

        # --- correct the corrupted move-line end (raw) ---
        cr.execute(
            "UPDATE stock_move_line SET %s = %%s WHERE id = %%s" % field,
            (suggested.id, ml.id))

        # --- re-align the two quants: +diff to the corrected-TO location,
        #     -diff to the corrected-FROM location (matches the hand-run) ---
        cr.execute(
            "UPDATE stock_quant SET quantity = quantity + %s WHERE id = %s",
            (diff, to_quant.id))
        cr.execute(
            "UPDATE stock_quant SET quantity = quantity - %s WHERE id = %s",
            (diff, from_quant.id))

        ML.invalidate_model()
        Quant.invalidate_model()
        self.state = 'fixed'
        return True
