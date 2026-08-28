# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime
import io
import base64
try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None
import logging

_logger = logging.getLogger(__name__)

# Quantity below which a layer counts as exhausted. Matches _run_fifo().
QTY_EPSILON = 1e-4

# Money rounding tolerance used when comparing values.
VALUE_EPSILON = 0.01


class FifoRecalculationWizard(models.TransientModel):
    """Repair the FIFO queue of stock.valuation.layer, warehouse by warehouse.

    This wizard used to delete valuation layers in a date range and rebuild
    them from stock.move. It no longer does, and must not again:

    * stock_valuation_layer is the sole book of record for stock value on this
      database. Product categories are FIFO + manual_periodic, so the vast
      majority of layers carry no account_move_id and no journal entry would
      ever surface a bad write.
    * Landed cost, manual revaluation and position layers have no stock move
      behind them. A rebuild that iterates stock.move cannot recreate them, so
      deleting them destroys value permanently.

    What it does instead: replay the FIFO engine over the layers that already
    exist, and correct remaining_qty / remaining_value where the stored queue
    state disagrees with the replay. Nothing is deleted, no layer is created,
    and `value` — the P&L number — is reported but never rewritten.
    """
    _name = 'fifo.recalculation.wizard'
    _description = 'Recalculate FIFO by Warehouse'

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Warehouses',
        required=True,
        help='Required. FIFO is queued per warehouse, so a replay is only '
             'meaningful within one. This also bounds the blast radius.'
    )
    product_ids = fields.Many2many(
        'product.product',
        string='Products',
        help='Leave empty for every product that has layers at the selected '
             'warehouses.'
    )
    product_categ_ids = fields.Many2many(
        'product.category',
        string='Product Categories',
        help='Used only when no explicit product is selected.'
    )

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    dry_run = fields.Boolean(
        string='Dry Run (report only, change nothing)',
        default=True,
        help='Leave enabled to see exactly which layers would change, and to '
             'what, without writing anything.'
    )
    include_reordered = fields.Boolean(
        string='Also repair products whose FIFO queue was reordered',
        default=False,
        help='A layer whose id order disagrees with its create_date order was '
             'inserted into the past by a backdating tool. The replay consumes '
             'in create_date order, which is not the order the live engine '
             'consumed in at the time, so its answer for that product is a '
             'guess. Off by default.'
    )
    max_mismatch_percent = fields.Float(
        string='Refuse to Apply Above Mismatch (%)',
        default=5.0,
        help='Sanity gate. If the replay disagrees with stored state on more '
             'than this share of the layers in scope, it is the replay that is '
             'suspect, not the data, and Apply is refused.'
    )

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    state = fields.Selection([
        ('draft', 'Draft'),
        ('preview', 'Preview'),
        ('done', 'Done'),
    ], default='draft', string='State')
    line_ids = fields.One2many(
        'fifo.recalculation.wizard.line',
        'wizard_id',
        string='Preview Lines',
        readonly=True
    )
    log_text = fields.Text(string='Log', readonly=True)
    backup_id = fields.Many2one(
        'fifo.recalculation.backup',
        string='Backup Reference',
        readonly=True
    )
    can_rollback = fields.Boolean(compute='_compute_can_rollback')
    can_apply = fields.Boolean(compute='_compute_can_apply')
    block_reason = fields.Char(readonly=True)

    layers_scanned = fields.Integer(readonly=True)
    layers_changed = fields.Integer(readonly=True)
    value_delta = fields.Float(
        string='Net Change in Remaining Value',
        digits='Product Price',
        readonly=True
    )
    pairs_blocked = fields.Integer(
        string='Product/Warehouse Pairs Skipped',
        readonly=True
    )
    cogs_mismatch_count = fields.Integer(
        string='Outgoing Layers With Value Mismatch',
        readonly=True
    )
    cogs_mismatch_value = fields.Float(
        string='Value Mismatch Total',
        digits='Product Price',
        readonly=True
    )

    excel_file = fields.Binary(string='Excel Export', readonly=True)
    excel_filename = fields.Char(readonly=True)

    @api.depends('backup_id', 'state')
    def _compute_can_rollback(self):
        for record in self:
            record.can_rollback = bool(
                record.backup_id
                and record.state == 'done'
                and record.backup_id.state == 'active'
            )

    @api.depends('state', 'block_reason', 'dry_run', 'layers_changed')
    def _compute_can_apply(self):
        for record in self:
            record.can_apply = bool(
                record.state == 'preview'
                and not record.block_reason
                and record.layers_changed
            )

    @api.constrains('max_mismatch_percent')
    def _check_max_mismatch_percent(self):
        for record in self:
            if not 0 < record.max_mismatch_percent <= 100:
                raise UserError(_('Mismatch gate must be between 0 and 100 percent.'))

    # ------------------------------------------------------------------
    # Scope resolution
    # ------------------------------------------------------------------

    def _scoped_product_ids(self, warehouse):
        """Product ids that have layers at `warehouse`, honouring the filters."""
        self.ensure_one()
        params = [warehouse.id, self.company_id.id]
        clause = ''
        if self.product_ids:
            clause = 'AND product_id IN %s'
            params.append(tuple(self.product_ids.ids))
        elif self.product_categ_ids:
            products = self.env['product.product'].search([
                ('categ_id', 'child_of', self.product_categ_ids.ids)
            ])
            if not products:
                return []
            clause = 'AND product_id IN %s'
            params.append(tuple(products.ids))

        self.env.cr.execute("""
            SELECT DISTINCT product_id
            FROM stock_valuation_layer
            WHERE warehouse_id = %%s AND company_id = %%s %s
            ORDER BY product_id
        """ % clause, tuple(params))
        return [row[0] for row in self.env.cr.fetchall()]

    def _locked_layer_ids(self, product_id, warehouse_id):
        """Layers the user has explicitly frozen.

        `locked` is nullable — rows created before this module was installed
        carry NULL, not False — so the test is IS TRUE, never = False.
        """
        self.env.cr.execute("""
            SELECT id FROM stock_valuation_layer
            WHERE product_id = %s AND warehouse_id = %s AND company_id = %s
              AND locked IS TRUE
        """, (product_id, warehouse_id, self.company_id.id))
        return {row[0] for row in self.env.cr.fetchall()}

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def action_preview(self):
        """Replay FIFO across the selected scope and report what would change."""
        self.ensure_one()
        self.line_ids.unlink()

        log = [
            '=== FIFO Queue Repair — Preview ===',
            'Time: %s' % datetime.now(),
            'Company: %s' % self.company_id.name,
            'Warehouses: %s' % ', '.join(self.warehouse_ids.mapped('name')),
            'Nothing is deleted or created. Only remaining_qty and',
            'remaining_value are ever written, and only on Apply.',
            '',
        ]

        analysis = self._analyse(log)

        lines = [dict(vals, wizard_id=self.id) for vals in analysis['line_vals']]
        self.env['fifo.recalculation.wizard.line'].create(lines)

        block_reason = self._evaluate_gate(analysis, log)

        self.write({
            'state': 'preview',
            'log_text': '\n'.join(log),
            'block_reason': block_reason,
            'layers_scanned': analysis['layers_scanned'],
            'layers_changed': len(analysis['changes']),
            'value_delta': analysis['value_delta'],
            'pairs_blocked': analysis['pairs_blocked'],
            'cogs_mismatch_count': analysis['cogs_mismatch_count'],
            'cogs_mismatch_value': analysis['cogs_mismatch_value'],
        })
        return self._reopen()

    def _analyse(self, log):
        """Replay every product/warehouse pair in scope and collect the diffs.

        Read-only. Returns the change set, the per-pair preview lines and the
        counters the gate and the summary need.
        """
        self.ensure_one()
        SVL = self.env['stock.valuation.layer']

        # The replay and every comparison below read with raw SQL, which does
        # not see values still sitting in the ORM cache. Push them to the
        # database first or the tool reports on data that is already stale.
        SVL.flush_model(['quantity', 'value', 'remaining_qty', 'remaining_value',
                         'locked', 'stock_landed_cost_id',
                         'stock_valuation_layer_id'])

        changes = []            # (layer_id, cur_qty, cur_value, new_qty, new_value)
        line_vals = []
        layers_scanned = 0
        layers_considered = 0   # only those in pairs that would actually be written
        pairs_blocked = 0
        cogs_mismatch_count = 0
        cogs_mismatch_value = 0.0
        value_delta = 0.0

        for warehouse in self.warehouse_ids:
            product_ids = self._scoped_product_ids(warehouse)
            log.append('--- %s: %s products with layers ---'
                       % (warehouse.name, len(product_ids)))

            for product_id in product_ids:
                result = SVL._fifo_replay_remaining(
                    product_id, warehouse.id, self.company_id.id)
                expected = result['expected']
                if not expected:
                    continue
                layers_scanned += len(expected)

                stored = self._read_stored(list(expected))
                locked_ids = self._locked_layer_ids(product_id, warehouse.id)

                # Outgoing value is compared, never corrected: rewriting `value`
                # on an outgoing layer fabricates COGS, and with no journal
                # entry behind it nothing would ever contradict the number.
                pair_cogs_count = 0
                pair_cogs_value = 0.0
                stored_values = self._read_stored_values(list(result['cogs']))
                for layer_id, expected_value in result['cogs'].items():
                    current = stored_values.get(layer_id, 0.0)
                    if abs(current - expected_value) > VALUE_EPSILON:
                        pair_cogs_count += 1
                        pair_cogs_value += expected_value - current
                cogs_mismatch_count += pair_cogs_count
                cogs_mismatch_value += pair_cogs_value

                # Why this pair may not be repaired.
                reasons = []
                if result['inverted'] and not self.include_reordered:
                    reasons.append(_('FIFO queue reordered (%s layers inserted '
                                     'into the past)') % result['inverted'])
                if result['shortage'] > QTY_EPSILON:
                    reasons.append(_('FIFO shortage of %.4f units — more was '
                                     'consumed than ever received')
                                   % result['shortage'])
                if locked_ids:
                    reasons.append(_('%s locked layers') % len(locked_ids))
                if abs(pair_cogs_value) > VALUE_EPSILON:
                    # The exact reason this is fatal, per product/warehouse:
                    #   book        B = SUM(value)          = IN + LC - COGS_stored
                    #   replay      R = SUM(remaining_value) = IN + LC - COGS_replay
                    #   R - B = COGS_stored - COGS_replay
                    # Writing remaining_value while leaving `value` on outgoing
                    # layers alone therefore pushes the queue out of step with
                    # the book by exactly that amount — which is the divergence
                    # this tool exists to close, not to create. Correcting
                    # `value` instead is not an option: it is the P&L number and
                    # no journal entry would ever contradict a wrong one.
                    reasons.append(_(
                        'Outgoing value disagrees with the replay by %.2f — '
                        'writing remaining_value here would push the FIFO queue '
                        'out of step with the book by that amount. The stored '
                        'COGS has to be settled first, by a person.'
                    ) % pair_cogs_value)

                pair_changes = []
                for layer_id, (new_qty, new_value) in expected.items():
                    if layer_id in locked_ids:
                        continue
                    cur_qty, cur_value = stored.get(layer_id, (0.0, 0.0))
                    if (abs(cur_qty - new_qty) > QTY_EPSILON
                            or abs(cur_value - new_value) > VALUE_EPSILON):
                        pair_changes.append(
                            (layer_id, cur_qty, cur_value, new_qty, new_value))

                qty_before = sum(v[0] for v in stored.values())
                value_before = sum(v[1] for v in stored.values())
                qty_after = sum(v[0] for v in expected.values())
                value_after = sum(v[1] for v in expected.values())

                if reasons:
                    pairs_blocked += 1
                else:
                    changes.extend(pair_changes)
                    layers_considered += len(expected)
                    value_delta += value_after - value_before

                if pair_changes or reasons or pair_cogs_count:
                    line_vals.append({
                        'product_id': product_id,
                        'warehouse_id': warehouse.id,
                        'qty_before': qty_before,
                        'value_before': value_before,
                        'qty_after': qty_after,
                        'value_after': value_after,
                        'diff_qty': qty_after - qty_before,
                        'diff_value': value_after - value_before,
                        'layer_change_count': len(pair_changes),
                        'shortage_qty': result['shortage'],
                        'reordered_layers': result['inverted'],
                        'cogs_mismatch_count': pair_cogs_count,
                        'cogs_mismatch_value': pair_cogs_value,
                        'skip_reason': '; '.join(reasons),
                    })

        log.append('')
        log.append('Layers scanned: %s' % layers_scanned)
        log.append('Layers to correct: %s' % len(changes))
        log.append('Product/warehouse pairs skipped: %s' % pairs_blocked)
        log.append('Net change in remaining value: %.2f' % value_delta)
        log.append('Outgoing layers whose value disagrees with the replay: '
                   '%s (%.2f) — reported only, never written'
                   % (cogs_mismatch_count, cogs_mismatch_value))

        return {
            'changes': changes,
            'line_vals': line_vals,
            'layers_scanned': layers_scanned,
            'layers_considered': layers_considered,
            'pairs_blocked': pairs_blocked,
            'cogs_mismatch_count': cogs_mismatch_count,
            'cogs_mismatch_value': cogs_mismatch_value,
            'value_delta': value_delta,
        }

    def _read_stored(self, layer_ids):
        if not layer_ids:
            return {}
        self.env.cr.execute("""
            SELECT id, remaining_qty, remaining_value
            FROM stock_valuation_layer WHERE id IN %s
        """, (tuple(layer_ids),))
        return {row[0]: (float(row[1] or 0.0), float(row[2] or 0.0))
                for row in self.env.cr.fetchall()}

    def _read_stored_values(self, layer_ids):
        if not layer_ids:
            return {}
        self.env.cr.execute("""
            SELECT id, value FROM stock_valuation_layer WHERE id IN %s
        """, (tuple(layer_ids),))
        return {row[0]: float(row[1] or 0.0) for row in self.env.cr.fetchall()}

    def _evaluate_gate(self, analysis, log):
        """Refuse to apply a replay that cannot reproduce most of stored state.

        The replay is a model of what the live FIFO engine did. If it disagrees
        with a large share of the layers it looked at, the model is wrong, and
        applying it would overwrite correct data with a bad guess.
        """
        if not analysis['layers_scanned']:
            return _('Nothing in scope. Select warehouses that have valuation layers.')

        # Measured over the layers that would actually be written: layers in a
        # skipped pair are not candidates, so counting them would dilute the
        # rate and let a bad replay through.
        considered = analysis['layers_considered']
        if not considered:
            return False

        rate = 100.0 * len(analysis['changes']) / considered
        log.append('Mismatch rate: %.2f%% (gate: %.2f%%)'
                   % (rate, self.max_mismatch_percent))

        if rate > self.max_mismatch_percent:
            reason = _(
                'Apply refused: the replay disagrees with %.2f%% of the layers '
                'in scope, above the %.2f%% gate. A replay that cannot '
                'reproduce stored state cannot be trusted to correct it. '
                'Narrow the scope to one product first and read the diff.'
            ) % (rate, self.max_mismatch_percent)
            log.append('')
            log.append(reason)
            return reason
        return False

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def action_apply(self):
        """Write the corrected remaining_qty / remaining_value.

        Re-runs the analysis rather than trusting the preview lines, so what is
        written is computed against the data as it stands right now.
        """
        self.ensure_one()

        if self.dry_run:
            raise UserError(_(
                'Dry Run is enabled. Uncheck it to write, after reading the '
                'preview.'))
        if self.state != 'preview':
            raise UserError(_('Run Preview first.'))
        if self.block_reason:
            raise UserError(self.block_reason)

        log = [
            '',
            '=== Applying ===',
            'Time: %s' % datetime.now(),
            'User: %s' % self.env.user.name,
        ]

        analysis = self._analyse(log)
        changes = analysis['changes']
        if not changes:
            raise UserError(_('Nothing to correct any more — the data changed '
                              'since the preview. Run Preview again.'))

        gate = self._evaluate_gate(analysis, log)
        if gate:
            raise UserError(gate)

        # Backup is mandatory. The previous version logged the failure and
        # carried on writing; there was then no way back.
        backup = self._create_backup([c[0] for c in changes])
        log.append('Backup %s created with %s layers.'
                   % (backup.name, backup.layer_count))

        for layer_id, cur_qty, cur_value, new_qty, new_value in changes:
            self.env.cr.execute("""
                UPDATE stock_valuation_layer
                SET remaining_qty = %s, remaining_value = %s
                WHERE id = %s
            """, (new_qty, new_value, layer_id))
            _logger.info(
                'fifo recalculation: layer %s remaining %.4f/%.2f -> %.4f/%.2f',
                layer_id, cur_qty, cur_value, new_qty, new_value)

        # The UPDATE went round the ORM. Without this, a cached copy of one of
        # these layers still holds the old value, and the next ORM flush in
        # this transaction would write it straight back over the correction.
        self.env['stock.valuation.layer'].invalidate_model(
            ['remaining_qty', 'remaining_value'])

        log.append('Applied %s layer corrections.' % len(changes))
        log.append('Net change in remaining value: %.2f' % analysis['value_delta'])
        log.append('`value` was not touched on any layer.')

        self.write({
            'state': 'done',
            'backup_id': backup.id,
            'layers_changed': len(changes),
            'value_delta': analysis['value_delta'],
            'log_text': (self.log_text or '') + '\n' + '\n'.join(log),
        })
        return self._reopen()

    def _create_backup(self, layer_ids):
        """Snapshot the layers about to change. Raises if it cannot.

        Rows are copied with a single INSERT ... SELECT: a repair covering a
        warehouse-year touches far too many layers for row-by-row ORM creates.
        """
        self.ensure_one()
        backup = self.env['fifo.recalculation.backup'].create({
            'company_id': self.company_id.id,
            'warehouse_ids': [fields.Command.set(self.warehouse_ids.ids)],
            'layer_count': len(layer_ids),
        })
        self.env.cr.execute("""
            INSERT INTO fifo_recalculation_backup_line
                (backup_id, layer_id, product_id, warehouse_id, quantity,
                 unit_cost, value, remaining_qty, remaining_value,
                 stock_move_id, description,
                 create_uid, create_date, write_uid, write_date)
            SELECT %s, l.id, l.product_id, l.warehouse_id, l.quantity,
                   l.unit_cost, l.value, l.remaining_qty, l.remaining_value,
                   l.stock_move_id, l.description,
                   %s, now() at time zone 'UTC', %s, now() at time zone 'UTC'
            FROM stock_valuation_layer l
            WHERE l.id IN %s
        """, (backup.id, self.env.uid, self.env.uid, tuple(layer_ids)))

        written = self.env.cr.rowcount
        if written != len(layer_ids):
            raise UserError(_(
                'Backup incomplete: %s of %s layers were snapshotted. '
                'Nothing has been written.') % (written, len(layer_ids)))

        # The INSERT went round the ORM, so backup.line_ids is still cached as
        # empty. Left stale, action_restore() would refuse the rollback on a
        # backup that is in fact complete.
        backup.invalidate_recordset(['line_ids'])
        return backup

    def action_rollback(self):
        self.ensure_one()
        if not self.can_rollback:
            raise UserError(_('Nothing to roll back.'))
        return self.backup_id.action_restore()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def action_export_excel(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_(
                'Python library xlsxwriter is not installed.\n'
                'Install it with: pip install xlsxwriter'))
        if not self.line_ids:
            raise UserError(_('No preview data to export. Run Preview first.'))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('FIFO Repair Preview')

        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#4472C4', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter'})
        number_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        text_format = workbook.add_format({'border': 1})
        positive_format = workbook.add_format(
            {'num_format': '#,##0.00', 'bg_color': '#C6EFCE', 'border': 1})
        negative_format = workbook.add_format(
            {'num_format': '#,##0.00', 'bg_color': '#FFC7CE', 'border': 1})

        headers = [
            'Product', 'Warehouse', 'Layers to Fix',
            'Remaining Qty Before', 'Remaining Value Before',
            'Remaining Qty After', 'Remaining Value After',
            'Qty Diff', 'Value Diff',
            'Shortage Qty', 'Reordered Layers',
            'Outgoing Value Mismatch', 'Mismatch Amount', 'Skipped Because',
        ]
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        worksheet.set_column(0, 0, 40)
        worksheet.set_column(1, 1, 25)
        worksheet.set_column(2, 12, 16)
        worksheet.set_column(13, 13, 50)

        row = 1
        for line in self.line_ids:
            worksheet.write(row, 0, line.product_id.display_name, text_format)
            worksheet.write(row, 1, line.warehouse_id.name or '', text_format)
            worksheet.write(row, 2, line.layer_change_count, number_format)
            worksheet.write(row, 3, line.qty_before, number_format)
            worksheet.write(row, 4, line.value_before, number_format)
            worksheet.write(row, 5, line.qty_after, number_format)
            worksheet.write(row, 6, line.value_after, number_format)
            qty_fmt = (positive_format if line.diff_qty > 0
                       else negative_format if line.diff_qty < 0 else number_format)
            val_fmt = (positive_format if line.diff_value > 0
                       else negative_format if line.diff_value < 0 else number_format)
            worksheet.write(row, 7, line.diff_qty, qty_fmt)
            worksheet.write(row, 8, line.diff_value, val_fmt)
            worksheet.write(row, 9, line.shortage_qty, number_format)
            worksheet.write(row, 10, line.reordered_layers, number_format)
            worksheet.write(row, 11, line.cogs_mismatch_count, number_format)
            worksheet.write(row, 12, line.cogs_mismatch_value, number_format)
            worksheet.write(row, 13, line.skip_reason or '', text_format)
            row += 1

        workbook.close()
        output.seek(0)

        filename = 'FIFO_Repair_%s.xlsx' % datetime.now().strftime('%Y%m%d_%H%M%S')
        self.write({
            'excel_file': base64.b64encode(output.read()),
            'excel_filename': filename,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content?model=%s&id=%s&field=excel_file&download=true'
                   '&filename=%s' % (self._name, self.id, filename),
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Scheduled run
    # ------------------------------------------------------------------

    @api.model
    def run_scheduled_recalculation(self, config_id=None):
        """Report-only scheduled replay.

        The cron never writes. Applying a valuation repair unattended, on a
        database whose layers carry no journal entry, means a wrong number can
        stand for a month before anyone looks. The cron produces the diff and
        emails it; a human decides.
        """
        if config_id:
            config = self.env['fifo.recalculation.config'].browse(config_id)
        else:
            config = self.env['fifo.recalculation.config'].search([
                ('active', '=', True), ('is_default', '=', True)
            ], limit=1)
        if not config or not config.warehouse_ids:
            return False

        wizard = self.create({
            'company_id': config.company_id.id,
            'warehouse_ids': [fields.Command.set(config.warehouse_ids.ids)],
            'product_ids': [fields.Command.set(config.product_ids.ids)],
            'product_categ_ids': [fields.Command.set(config.product_categ_ids.ids)],
            'dry_run': True,
        })
        wizard.action_preview()
        if config.notification_user_ids:
            wizard._send_notification(config.notification_user_ids)
        return True

    def _send_notification(self, users):
        self.ensure_one()
        emails = [email for email in users.mapped('email') if email]
        if not emails:
            return
        body = _(
            '<p>Scheduled FIFO queue check (report only — nothing was '
            'written).</p>'
            '<ul>'
            '<li>Warehouses: %s</li>'
            '<li>Layers scanned: %s</li>'
            '<li>Layers that disagree with the replay: %s</li>'
            '<li>Net change if corrected: %.2f</li>'
            '</ul><pre>%s</pre>'
        ) % (
            ', '.join(self.warehouse_ids.mapped('name')),
            self.layers_scanned, self.layers_changed, self.value_delta,
            self.log_text or '',
        )
        self.env['mail.mail'].sudo().create({
            'subject': _('FIFO Queue Check: %s') % self.company_id.name,
            'body_html': body,
            'email_to': ','.join(emails),
        }).send()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class FifoRecalculationWizardLine(models.TransientModel):
    """One product/warehouse pair in the preview."""
    _name = 'fifo.recalculation.wizard.line'
    _description = 'Recalculated FIFO Preview Line'
    _order = 'skip_reason desc, layer_change_count desc'

    wizard_id = fields.Many2one(
        'fifo.recalculation.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', required=True, string='Product')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')

    qty_before = fields.Float(
        string='Remaining Qty Before', digits='Product Unit of Measure')
    value_before = fields.Float(
        string='Remaining Value Before', digits='Product Price')
    qty_after = fields.Float(
        string='Remaining Qty After', digits='Product Unit of Measure')
    value_after = fields.Float(
        string='Remaining Value After', digits='Product Price')
    diff_qty = fields.Float(string='Qty Diff', digits='Product Unit of Measure')
    diff_value = fields.Float(string='Value Diff', digits='Product Price')

    layer_change_count = fields.Integer(string='Layers to Fix')
    shortage_qty = fields.Float(
        string='FIFO Shortage', digits='Product Unit of Measure',
        help='Quantity consumed with nothing left in the queue to consume it '
             'from. The replay cannot invent the missing stock.')
    reordered_layers = fields.Integer(
        string='Reordered Layers',
        help='Layers whose id order disagrees with their create_date order — '
             'inserted into the past by a backdating tool.')
    cogs_mismatch_count = fields.Integer(string='Outgoing Value Mismatch')
    cogs_mismatch_value = fields.Float(
        string='Mismatch Amount', digits='Product Price',
        help='Difference between the value stored on outgoing layers and what '
             'the replay computes. Reported only — never corrected here.')
    skip_reason = fields.Char(
        string='Skipped Because',
        help='Filled in when this pair will not be repaired.')
