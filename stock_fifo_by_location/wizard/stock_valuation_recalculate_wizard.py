# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

# Quantity below which a layer counts as exhausted. Matches the clamp in
# stock.valuation.layer._run_fifo().
QTY_EPSILON = 1e-4

# Money rounding tolerance used when reporting differences.
VALUE_EPSILON = 0.01


class StockValuationRecalculateWizard(models.TransientModel):
    """Rebuild remaining_qty / remaining_value from the valuation layer history.

    This wizard is a repair tool, not routine maintenance. It writes directly to
    stock_valuation_layer, the sole book of record for stock value on this
    database (product categories are FIFO + manual_periodic, so there are no
    journal entries that would ever surface a bad write). Everything therefore
    defaults to a dry run, and every operation is opt-in.
    """
    _name = 'stock.valuation.recalculate.wizard'
    _description = 'Recalculate Stock Valuation by Warehouse'

    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Warehouses',
        required=True,
        help='Warehouses to process. Required: it bounds both the write '
             'transaction and the blast radius.'
    )

    dry_run = fields.Boolean(
        string='Dry Run (report only, change nothing)',
        default=True,
        help='Leave enabled to see exactly which layers would change, and to '
             'what, without writing anything.'
    )

    recalculate_remaining = fields.Boolean(
        string='Rebuild Remaining Qty/Value',
        default=False,
        help='Replay FIFO chronologically per product per warehouse and rewrite '
             'remaining_qty / remaining_value to match.'
    )

    fix_null_remaining = fields.Boolean(
        string='Set NULL Remaining Value to 0 (outgoing layers)',
        default=False,
        help='Outgoing layers should carry remaining_value = 0, not NULL.'
    )

    fix_negative_remaining = fields.Boolean(
        string='Reset Incoming Layers With Negative Remaining',
        default=False,
        help='An incoming layer with remaining_qty < 0 means more was consumed '
             'from it than it ever held. Resetting it to its original quantity '
             'hides the over-consumption rather than explaining it, so read the '
             'dry run before enabling this.'
    )

    fix_excess_remaining = fields.Boolean(
        string='Cap Incoming Layers With Excess Remaining',
        default=False,
        help='Cap remaining_qty at the layer quantity where it somehow exceeds it.'
    )

    diagnose_value_residual = fields.Boolean(
        string='Report Value Residual (read-only)',
        default=True,
        help='List product/warehouse pairs whose net quantity is ~0 but whose '
             'value is not explained by zero-quantity layers. Reports only.'
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('processing', 'Processing'),
        ('done', 'Done'),
    ], default='draft')

    result_message = fields.Html(
        string='Result',
        readonly=True
    )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def action_recalculate(self):
        self.ensure_one()

        operations = [
            self.recalculate_remaining, self.fix_null_remaining,
            self.fix_negative_remaining, self.fix_excess_remaining,
            self.diagnose_value_residual,
        ]
        if not any(operations):
            raise UserError(_('Please select at least one operation to perform.'))

        if not self.warehouse_ids:
            raise UserError(_('Please select at least one warehouse.'))

        self.state = 'processing'

        # Everything below reads and writes stock_valuation_layer with raw SQL,
        # which neither sees nor is seen by the ORM cache. Flush first so the
        # report is about the data as it actually stands.
        self.env['stock.valuation.layer'].flush_model(
            ['quantity', 'value', 'remaining_qty', 'remaining_value',
             'stock_landed_cost_id', 'stock_valuation_layer_id'])

        mode = 'DRY RUN — nothing was written' if self.dry_run else 'APPLIED'
        html = ['<div style="font-family: monospace;">']
        html.append('<h3>Valuation Recalculation — %s</h3>' % mode)
        html.append('<p>Warehouses: %s</p>' % ', '.join(self.warehouse_ids.mapped('name')))

        if self.fix_null_remaining:
            html += self._run_fix_null_remaining()

        if self.fix_negative_remaining:
            html += self._run_simple_fix(
                'Incoming layers with negative remaining',
                "quantity > 0 AND remaining_qty < 0",
                lambda qty, value, rq, rv: (qty, value),
            )

        if self.fix_excess_remaining:
            html += self._run_simple_fix(
                'Incoming layers with remaining above quantity',
                "quantity > 0 AND remaining_qty > quantity",
                lambda qty, value, rq, rv: (qty, value),
            )

        if self.recalculate_remaining:
            html += self._run_rebuild_remaining()

        if self.diagnose_value_residual:
            html += self._run_diagnose_value_residual()

        html.append('</div>')

        if not self.dry_run:
            # The UPDATEs went round the ORM; drop any cached copy so a later
            # flush in this transaction cannot write the old values back.
            self.env['stock.valuation.layer'].invalidate_model(
                ['remaining_qty', 'remaining_value'])

        self.write({'state': 'done', 'result_message': ''.join(html)})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.valuation.recalculate.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # FIFO replay
    # ------------------------------------------------------------------

    def _replay_fifo(self, warehouse_id, product_id):
        """Replay the FIFO engine for one product at one warehouse.

        The replay itself lives on stock.valuation.layer so that this wizard
        and fifo.recalculation.wizard cannot drift apart on what the queue
        should be holding. See _fifo_replay_remaining() for the semantics.

        Returns (expected, shortage) where expected maps layer id to the
        (remaining_qty, remaining_value) the engine should be holding.
        """
        result = self.env['stock.valuation.layer']._fifo_replay_remaining(
            product_id, warehouse_id, self.env.company.id)
        return result['expected'], result['shortage']

    def _cogs_gap(self, cogs):
        """How far the stored outgoing values sit from the replayed ones."""
        if not cogs:
            return 0.0
        self.env.cr.execute(
            'SELECT id, value FROM stock_valuation_layer WHERE id IN %s',
            (tuple(cogs),))
        stored = {row[0]: float(row[1] or 0.0) for row in self.env.cr.fetchall()}
        return sum(expected - stored.get(layer_id, 0.0)
                   for layer_id, expected in cogs.items())

    def _run_rebuild_remaining(self):
        html = ['<h4>Rebuild Remaining Qty/Value</h4>']

        changes = []
        shortages = []
        desynced = []
        products_seen = 0

        for warehouse in self.warehouse_ids:
            self.env.cr.execute("""
                SELECT DISTINCT product_id
                FROM stock_valuation_layer
                WHERE warehouse_id = %s AND company_id = %s
                ORDER BY product_id
            """, (warehouse.id, self.env.company.id))
            product_ids = [r[0] for r in self.env.cr.fetchall()]

            for product_id in product_ids:
                products_seen += 1
                result = self.env['stock.valuation.layer']._fifo_replay_remaining(
                    product_id, warehouse.id, self.env.company.id)
                expected, shortage = result['expected'], result['shortage']
                if shortage > QTY_EPSILON:
                    shortages.append((warehouse.id, product_id, shortage))

                if not expected:
                    continue

                # Per product/warehouse:
                #     book   B = SUM(value)           = IN + LC - COGS_stored
                #     replay R = SUM(remaining_value) = IN + LC - COGS_replay
                #     R - B = COGS_stored - COGS_replay
                # So where the stored outgoing value disagrees with the replay,
                # writing remaining_value pushes the queue out of step with the
                # book by exactly that amount. Correcting `value` instead is not
                # an option — it is the P&L number, and on this database no
                # journal entry would ever contradict a wrong one. Skip the pair
                # and let a person settle the COGS first.
                cogs_gap = self._cogs_gap(result['cogs'])
                if abs(cogs_gap) > VALUE_EPSILON:
                    desynced.append((warehouse.id, product_id, cogs_gap))
                    continue

                self.env.cr.execute("""
                    SELECT id, remaining_qty, remaining_value
                    FROM stock_valuation_layer
                    WHERE id IN %s
                """, (tuple(expected),))
                for layer_id, cur_qty, cur_value in self.env.cr.fetchall():
                    new_qty, new_value = expected[layer_id]
                    cur_qty = cur_qty or 0.0
                    cur_value = cur_value or 0.0
                    if (abs(float(cur_qty) - new_qty) > QTY_EPSILON
                            or abs(float(cur_value) - new_value) > VALUE_EPSILON):
                        changes.append((layer_id, float(cur_qty), float(cur_value),
                                        new_qty, new_value))

        html.append('<p>Scanned %s product/warehouse combinations.</p>' % products_seen)
        html.append('<p>Layers that differ from the replay: <b>%s</b></p>' % len(changes))

        if desynced:
            total = sum(gap for _wh, _prod, gap in desynced)
            html.append(
                '<p style="color:#b35c00;">Skipped %s product/warehouse '
                'combinations (%.2f in total) whose stored outgoing value '
                'disagrees with the replay. Rebuilding remaining_value there '
                'would push the FIFO queue out of step with the book by that '
                'amount. The outgoing values have to be settled first, by a '
                'person — this wizard will not rewrite them.</p>'
                % (len(desynced), total))

        if shortages:
            html.append(
                '<p style="color:#b35c00;">FIFO shortage detected on %s '
                'product/warehouse combinations — outgoing quantity exceeded '
                'everything ever received at that warehouse. The replay cannot '
                'invent the missing stock, so those layers rebuild to zero. '
                'Receive the stock first, then re-run.</p>' % len(shortages)
            )

        html.append(self._render_change_sample(changes))

        if changes and not self.dry_run:
            for layer_id, _cq, _cv, new_qty, new_value in changes:
                self.env.cr.execute("""
                    UPDATE stock_valuation_layer
                    SET remaining_qty = %s, remaining_value = %s
                    WHERE id = %s
                """, (new_qty, new_value, layer_id))
                _logger.info(
                    "recalculate wizard: layer %s remaining %.4f/%.2f -> %.4f/%.2f",
                    layer_id, _cq, _cv, new_qty, new_value)
            html.append('<p><b>Applied %s updates.</b></p>' % len(changes))
            html.append(
                '<p style="color:#b35c00;">origin_remaining_qty / '
                'origin_remaining_value were NOT rebuilt. Replaying those needs '
                'to know, per move, whether it was an internal transfer or a '
                'real outgoing move, which the layer alone does not record.</p>'
            )

        return html

    # ------------------------------------------------------------------
    # Narrow fixes
    # ------------------------------------------------------------------

    def _run_fix_null_remaining(self):
        html = ['<h4>NULL Remaining Value on Outgoing Layers</h4>']
        self.env.cr.execute("""
            SELECT count(*) FROM stock_valuation_layer
            WHERE quantity < 0 AND remaining_value IS NULL AND warehouse_id IN %s
        """, (tuple(self.warehouse_ids.ids),))
        count = self.env.cr.fetchone()[0]
        html.append('<p>Layers affected: <b>%s</b></p>' % count)

        if count and not self.dry_run:
            self.env.cr.execute("""
                UPDATE stock_valuation_layer SET remaining_value = 0.0
                WHERE quantity < 0 AND remaining_value IS NULL AND warehouse_id IN %s
            """, (tuple(self.warehouse_ids.ids),))
            html.append('<p><b>Applied.</b></p>')
        return html

    def _run_simple_fix(self, title, condition, new_values):
        """Report, and optionally apply, a per-layer reset described by `condition`.

        `new_values(quantity, value, remaining_qty, remaining_value)` returns the
        (remaining_qty, remaining_value) to write.
        """
        html = ['<h4>%s</h4>' % title]
        self.env.cr.execute("""
            SELECT id, quantity, value, remaining_qty, remaining_value
            FROM stock_valuation_layer
            WHERE %s AND warehouse_id IN %%s
            ORDER BY id
        """ % condition, (tuple(self.warehouse_ids.ids),))
        rows = self.env.cr.fetchall()

        changes = []
        for layer_id, qty, value, rem_qty, rem_value in rows:
            new_qty, new_value = new_values(
                float(qty or 0), float(value or 0),
                float(rem_qty or 0), float(rem_value or 0))
            changes.append((layer_id, float(rem_qty or 0), float(rem_value or 0),
                            new_qty, new_value))

        html.append('<p>Layers affected: <b>%s</b></p>' % len(changes))
        html.append(self._render_change_sample(changes))

        if changes and not self.dry_run:
            for layer_id, _cq, _cv, new_qty, new_value in changes:
                self.env.cr.execute("""
                    UPDATE stock_valuation_layer
                    SET remaining_qty = %s, remaining_value = %s
                    WHERE id = %s
                """, (new_qty, new_value, layer_id))
                _logger.info(
                    "recalculate wizard: layer %s remaining %.4f/%.2f -> %.4f/%.2f",
                    layer_id, _cq, _cv, new_qty, new_value)
            html.append('<p><b>Applied %s updates.</b></p>' % len(changes))
        return html

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _run_diagnose_value_residual(self):
        """Report product/warehouse pairs holding value with no quantity behind it.

        This used to rewrite `value` on outgoing layers until the totals summed
        to zero. That fabricates COGS, and because these layers carry no
        account_move_id there is no journal entry that would ever contradict it.
        The premise was wrong as well: a landed-cost or revaluation layer leaves
        value behind on purpose, so the expected residual is the sum of those
        zero-quantity layers, not zero.
        """
        html = ['<h4>Value Residual (read-only)</h4>']
        self.env.cr.execute("""
            SELECT warehouse_id, product_id,
                   SUM(value) AS total_value,
                   SUM(value) FILTER (WHERE quantity = 0) AS zero_qty_value
            FROM stock_valuation_layer
            WHERE warehouse_id IN %s AND company_id = %s
            GROUP BY warehouse_id, product_id
            HAVING ABS(SUM(quantity)) < 0.01
               AND ABS(SUM(value) - COALESCE(SUM(value) FILTER (WHERE quantity = 0), 0)) > 0.01
            ORDER BY ABS(SUM(value) - COALESCE(SUM(value) FILTER (WHERE quantity = 0), 0)) DESC
        """, (tuple(self.warehouse_ids.ids), self.env.company.id))
        rows = self.env.cr.fetchall()

        html.append('<p>Product/warehouse pairs with unexplained residual value: '
                    '<b>%s</b></p>' % len(rows))
        if rows:
            html.append('<table border="1" cellpadding="3" style="border-collapse:collapse;">')
            html.append('<tr><th>Warehouse</th><th>Product</th><th>Total value</th>'
                        '<th>Zero-qty value</th><th>Unexplained</th></tr>')
            for warehouse_id, product_id, total_value, zero_qty_value in rows[:50]:
                zero_qty_value = zero_qty_value or 0.0
                warehouse = self.env['stock.warehouse'].browse(warehouse_id)
                product = self.env['product.product'].browse(product_id)
                html.append(
                    '<tr><td>%s</td><td>%s</td><td align="right">%.2f</td>'
                    '<td align="right">%.2f</td><td align="right">%.2f</td></tr>' % (
                        warehouse.name or '-', product.display_name,
                        total_value, zero_qty_value, total_value - zero_qty_value))
            html.append('</table>')
            if len(rows) > 50:
                html.append('<p>... and %s more.</p>' % (len(rows) - 50))
            html.append(
                '<p>These are reported, never auto-corrected: the fix depends on '
                'why the residual is there, and rewriting outgoing values to '
                'force a zero total would only hide it.</p>')
        return html

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _render_change_sample(self, changes, limit=25):
        if not changes:
            return ''
        html = ['<table border="1" cellpadding="3" style="border-collapse:collapse;">']
        html.append('<tr><th>Layer</th><th>remaining_qty</th><th>remaining_value</th></tr>')
        for layer_id, cur_qty, cur_value, new_qty, new_value in changes[:limit]:
            html.append(
                '<tr><td>%s</td><td align="right">%.4f &rarr; %.4f</td>'
                '<td align="right">%.2f &rarr; %.2f</td></tr>' % (
                    layer_id, cur_qty, new_qty, cur_value, new_value))
        html.append('</table>')
        if len(changes) > limit:
            html.append('<p>... and %s more.</p>' % (len(changes) - limit))
        return ''.join(html)

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}
