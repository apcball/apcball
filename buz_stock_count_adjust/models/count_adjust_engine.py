from datetime import datetime, time, timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

# Thailand has no DST, so Bangkok is always a fixed UTC+7 offset.
BANGKOK_OFFSET = timedelta(hours=7)


class _DryRunRollback(Exception):
    """Private control-flow exception: unwinds the run() savepoint on a
    dry-run so a preview leaves the database exactly as it found it."""
    pass


class CountAdjustEngine(models.AbstractModel):
    _name = 'count.adjust.engine'
    _description = 'Stock Count Adjustment Engine'

    def _cutoff_instants(self, cutoff_date):
        """Return (utc_cutoff_dt, accounting_dt) as naive datetimes.

        utc_cutoff_dt is the UTC instant at which Bangkok day `cutoff_date`
        ends (start of the next Bangkok day, shifted back 7h to UTC).
        accounting_dt is midnight of the cutoff day, used as the SVL
        accounting_date for counter / bucket layers.
        """
        d = fields.Date.to_date(cutoff_date)
        utc_cutoff = datetime.combine(d + timedelta(days=1), time.min) - BANGKOK_OFFSET
        accounting_dt = datetime.combine(d, time.min)
        return utc_cutoff, accounting_dt

    def _check_category(self, product, company):
        """Reason string when the product's category posts real-time journal
        entries (GL reposting is out of scope for v1), else False.

        property_valuation is company_dependent -- resolve it against the
        adjustment's company, never self.env.company.
        """
        if product.with_company(company).categ_id.property_valuation == 'real_time':
            return _('Product category %s posts real-time journal entries; '
                     'GL reposting is out of scope for v1.') % product.categ_id.name
        return False

    def _gl_backed_layer_count(self, group, cutoff_date):
        """Number of in-scope post-cutoff SVL rows for the pair that already
        carry a journal entry (account_move_id IS NOT NULL).

        A product that was real_time when those moves were booked and later
        switched to manual_periodic slips past _check_category's current-setting
        read, yet _scoped_replay would still rewrite `value` on layers with a
        live account_move_id -- desyncing SVL from the GL. Reposting the GL is
        out of scope, so such a pair must not be touched.
        """
        product = group.product_id
        warehouse = group.warehouse_id
        company = group.adjustment_id.company_id
        utc_cutoff, _acct = self._cutoff_instants(cutoff_date)
        cr = self.env.cr
        cr.execute("""
            SELECT COUNT(*) FROM stock_valuation_layer
            WHERE product_id = %s AND warehouse_id = %s AND company_id = %s
              AND create_date > %s AND account_move_id IS NOT NULL
        """, (product.id, warehouse.id, company.id, utc_cutoff))
        return cr.fetchone()[0]

    def _baseline(self, adjustment):
        """dict {(product_id, warehouse_id): (Q0, V0)} at adjustment.cutoff_date.

        Builds the stock.fifo.valuation.report SQL view ONCE for every
        (product, warehouse) pair in scope, then a single search_read.
        Pairs with no report row get (0.0, 0.0).
        """
        pairs = {(l.product_id.id, l.warehouse_id.id) for l in adjustment.line_ids}
        product_ids = list({p for p, _w in pairs})
        warehouse_ids = list({w for _p, w in pairs})
        Report = self.env['stock.fifo.valuation.report']
        wiz = self.env['stock.fifo.valuation.report.wizard'].create({
            'date_from': '1900-01-01',
            'date_to': adjustment.cutoff_date,
            'product_ids': [fields.Command.set(product_ids)],
            'warehouse_ids': [fields.Command.set(warehouse_ids)],
        })
        # build the view once from this wizard record's filter fields
        Report.init_results(wiz)
        # init_results does DROP VIEW / CREATE VIEW but the ORM keeps its cache
        # for this model, so a second _baseline call in the same transaction
        # would search_read stale rows. Drop the cache before reading.
        Report.invalidate_model()
        rows = Report.search_read(
            [('product_id', 'in', product_ids),
             ('warehouse_id', 'in', warehouse_ids)],
            ['product_id', 'warehouse_id', 'ending_qty', 'ending_value'])
        base = {(r['product_id'][0], r['warehouse_id'][0]):
                (r['ending_qty'], r['ending_value']) for r in rows}
        return {pair: base.get(pair, (0.0, 0.0)) for pair in pairs}

    def _pair_layer_ids(self, group, cutoff_date):
        """(pre_ids, post_ids) for one (product, warehouse) group.

        pre_ids  -- SVL ids with COALESCE(accounting_date, create_date) < the
                    UTC cutoff instant (the rows _void_and_reseed step-3 zeroes).
        post_ids -- SVL ids with create_date > the UTC cutoff instant (the rows
                    _scoped_replay step-2 reprices).
        A backdated layer (pre-cutoff accounting_date, post-cutoff create_date)
        legitimately appears in BOTH lists -- callers must union, never add.
        """
        product = group.product_id
        warehouse = group.warehouse_id
        company = group.adjustment_id.company_id
        utc_cutoff, _acct = self._cutoff_instants(cutoff_date)
        cr = self.env.cr
        cr.execute("""
            SELECT id FROM stock_valuation_layer
            WHERE product_id = %s AND warehouse_id = %s AND company_id = %s
              AND COALESCE(accounting_date, create_date) < %s
        """, (product.id, warehouse.id, company.id, utc_cutoff))
        pre_ids = [r[0] for r in cr.fetchall()]
        cr.execute("""
            SELECT id FROM stock_valuation_layer
            WHERE product_id = %s AND warehouse_id = %s AND company_id = %s
              AND create_date > %s
        """, (product.id, warehouse.id, company.id, utc_cutoff))
        post_ids = [r[0] for r in cr.fetchall()]
        return pre_ids, post_ids

    def _locked_layer_count(self, group):
        """Number of pair SVL rows the user has frozen (locked IS TRUE).

        `locked` is nullable and may not exist at all on a DB that never
        installed the recal module -- guard with information_schema, and only
        ever test IS TRUE (NULL is not frozen).
        """
        cr = self.env.cr
        cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'stock_valuation_layer' AND column_name = 'locked'
        """)
        if not cr.fetchone():
            return 0
        product = group.product_id
        warehouse = group.warehouse_id
        company = group.adjustment_id.company_id
        cr.execute("""
            SELECT count(*) FROM stock_valuation_layer
            WHERE product_id = %s AND warehouse_id = %s AND company_id = %s
              AND locked IS TRUE
        """, (product.id, warehouse.id, company.id))
        return cr.fetchone()[0]

    def _reserved_qty(self, group):
        """Total stock.quant.reserved_quantity for the pair over the
        warehouse lot_stock_id subtree. Uses the SAME search domain
        _quant_adjust uses so the two never disagree about scope."""
        product = group.product_id
        warehouse = group.warehouse_id
        company = group.adjustment_id.company_id
        Quant = self.env['stock.quant']
        Quant.flush_model(['reserved_quantity'])
        quants = Quant.search([
            ('product_id', '=', product.id),
            ('location_id', 'child_of', warehouse.lot_stock_id.id),
            ('company_id', '=', company.id)])
        return sum(quants.mapped('reserved_quantity'))

    def _touch_scope(self, adjustment, base):
        """Every row a real run WILL touch, enumerated before anything is
        touched. `base` is the _baseline dict (unused here; kept for run()
        signature parity).

        Returns {'svl_ids': set, 'quant_ids': set, 'move_ids': set,
        'move_line_ids': set}.
        """
        self.env['stock.valuation.layer'].flush_model()
        self.env['stock.quant'].flush_model()
        cr = self.env.cr
        Quant = self.env['stock.quant']
        ML = self.env['stock.move.line']
        scope = {'svl_ids': set(), 'quant_ids': set(),
                 'move_ids': set(), 'move_line_ids': set()}
        for group in adjustment._line_groups():
            pre_ids, post_ids = self._pair_layer_ids(group, adjustment.cutoff_date)
            scope['svl_ids'].update(pre_ids)
            scope['svl_ids'].update(post_ids)

            quants = Quant.search([
                ('product_id', '=', group.product_id.id),
                ('location_id', 'child_of', group.warehouse_id.lot_stock_id.id),
                ('company_id', '=', group.adjustment_id.company_id.id)])
            scope['quant_ids'].update(quants.ids)

            if post_ids:
                cr.execute("""
                    SELECT DISTINCT stock_move_id FROM stock_valuation_layer
                    WHERE id IN %s AND stock_move_id IS NOT NULL
                """, (tuple(post_ids),))
                move_ids = [r[0] for r in cr.fetchall()]
                scope['move_ids'].update(move_ids)
                if move_ids:
                    mls = ML.search([('move_id', 'in', move_ids)])
                    scope['move_line_ids'].update(mls.ids)
        return scope

    def _snapshot(self, adjustment, scope):
        """Copy the pre-image of every scope row into the backup line tables
        (INSERT ... SELECT, never row-by-row ORM create -- a real run touches
        far too many rows). Raises UserError on any rowcount mismatch, before
        anything else runs.

        MUST be called BEFORE _void_and_reseed: the counter / bucket layers it
        inserts carry a pre-cutoff accounting_date, so if _snapshot ran after,
        they would land in svl_ids tagged was_inserted=false and a rollback
        would UPDATE-back rather than DELETE them.
        """
        cr = self.env.cr
        uid = self.env.uid
        backup = self.env['stock.count.adjustment.backup'].create({
            'company_id': adjustment.company_id.id,
            'adjustment_id': adjustment.id,
            'state': 'active',
        })
        svl_ids = scope['svl_ids']
        quant_ids = scope['quant_ids']
        ml_ids = scope['move_line_ids']

        if svl_ids:
            self.env['stock.valuation.layer'].flush_model(
                ['quantity', 'value', 'unit_cost', 'remaining_qty',
                 'remaining_value', 'accounting_date'])
            cr.execute("""
                INSERT INTO stock_count_adjustment_backup_line
                    (backup_id, layer_id, product_id, warehouse_id, quantity,
                     value, unit_cost, remaining_qty, remaining_value,
                     accounting_date, was_inserted,
                     create_uid, create_date, write_uid, write_date)
                SELECT %s, l.id, l.product_id, l.warehouse_id, l.quantity,
                       l.value, l.unit_cost, l.remaining_qty, l.remaining_value,
                       l.accounting_date, false,
                       %s, now() at time zone 'UTC', %s, now() at time zone 'UTC'
                FROM stock_valuation_layer l
                WHERE l.id IN %s
            """, (backup.id, uid, uid, tuple(svl_ids)))
            if cr.rowcount != len(svl_ids):
                raise UserError(_(
                    'Backup incomplete: %s of %s SVL rows snapshotted. '
                    'Nothing has been written.') % (cr.rowcount, len(svl_ids)))

        if quant_ids:
            self.env['stock.quant'].flush_model(['quantity'])
            cr.execute("""
                INSERT INTO stock_count_adjustment_backup_quant
                    (backup_id, quant_id, quantity,
                     create_uid, create_date, write_uid, write_date)
                SELECT %s, q.id, q.quantity,
                       %s, now() at time zone 'UTC', %s, now() at time zone 'UTC'
                FROM stock_quant q
                WHERE q.id IN %s
            """, (backup.id, uid, uid, tuple(quant_ids)))
            if cr.rowcount != len(quant_ids):
                raise UserError(_(
                    'Backup incomplete: %s of %s quant rows snapshotted. '
                    'Nothing has been written.') % (cr.rowcount, len(quant_ids)))

        if ml_ids:
            self.env['stock.move.line'].flush_model(
                ['location_id', 'location_dest_id', 'date'])
            self.env['stock.move'].flush_model(['date'])
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
                WHERE sml.id IN %s
            """, (backup.id, uid, uid, tuple(ml_ids)))
            if cr.rowcount != len(ml_ids):
                raise UserError(_(
                    'Backup incomplete: %s of %s move-line rows snapshotted. '
                    'Nothing has been written.') % (cr.rowcount, len(ml_ids)))

        backup.invalidate_recordset(
            ['line_ids', 'quant_line_ids', 'moveline_line_ids'])
        return backup

    def _void_and_reseed(self, group, q0, v0, cutoff_date, backup=None):
        """Void the pre-cutoff FIFO queue for one (product, warehouse) group
        and reseed it with one bucket layer per group line, so the ending
        queue at the cutoff instant equals the counted target.

        Writes stock.valuation.layer rows via raw SQL INSERT (never ORM
        create(), which stamps create_date=now() and fires _run_fifo).

        Returns {'counter_id': int, 'bucket_ids': [int], 'zeroed_ids': [int]}.
        """
        product = group.product_id
        warehouse = group.warehouse_id
        company = group.adjustment_id.company_id
        utc_cutoff, accounting_dt = self._cutoff_instants(cutoff_date)
        cr = self.env.cr
        uid = self.env.uid

        # Every INSERT / UPDATE below is raw SQL that cannot see rows still
        # sitting in the ORM write buffer, and a later ORM flush would clobber
        # our raw remaining_* zeroing. Push pending writes to the DB first.
        SVL = self.env['stock.valuation.layer']
        SVL.flush_model(['quantity', 'value', 'unit_cost', 'remaining_qty',
                         'remaining_value', 'origin_remaining_qty',
                         'origin_remaining_value', 'accounting_date'])
        categ_id = product.categ_id.id
        description = 'count-adjust %s' % group.adjustment_id.name

        def _insert(quantity, value, remaining_qty, remaining_value, created_at):
            unit_cost = value / quantity if quantity else 0.0
            cr.execute("""
                INSERT INTO stock_valuation_layer
                    (product_id, company_id, warehouse_id, categ_id,
                     quantity, value, unit_cost,
                     remaining_qty, remaining_value,
                     origin_remaining_qty, origin_remaining_value,
                     accounting_date, description, stock_move_id,
                     create_uid, create_date, write_uid, write_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL,
                        %s, %s, %s, now() at time zone 'UTC')
                RETURNING id
            """, (product.id, company.id, warehouse.id, categ_id,
                  quantity, value, unit_cost,
                  remaining_qty, remaining_value,
                  remaining_qty if quantity > 0 else 0.0,
                  remaining_value if quantity > 0 else 0.0,
                  accounting_dt, description,
                  uid, created_at, uid))
            return cr.fetchone()[0]

        counter_id = _insert(-q0, -v0, 0.0, 0.0,
                             utc_cutoff - timedelta(seconds=3))

        bucket_ids = []
        for n, line in enumerate(group.sorted(lambda l: (l.bucket_seq, l.id))):
            bucket_ids.append(_insert(
                line.target_qty, line.target_value,
                line.target_qty, line.target_value,
                utc_cutoff - timedelta(seconds=2) + timedelta(milliseconds=n)))

        inserted = tuple([counter_id] + bucket_ids)
        cr.execute("""
            UPDATE stock_valuation_layer
            SET remaining_qty = 0, remaining_value = 0
            WHERE product_id = %s AND warehouse_id = %s AND company_id = %s
              AND id NOT IN %s
              AND COALESCE(accounting_date, create_date) < %s
            RETURNING id
        """, (product.id, warehouse.id, company.id, inserted, utc_cutoff))
        zeroed_ids = [r[0] for r in cr.fetchall()]

        SVL.invalidate_model([
            'quantity', 'value', 'unit_cost', 'remaining_qty', 'remaining_value',
            'origin_remaining_qty', 'origin_remaining_value', 'accounting_date'])

        # Invariant check reads SUM straight from SQL over the inserted ids --
        # do NOT browse() the rows back through the ORM just to re-add numbers
        # we control.
        q_target = sum(group.mapped('target_qty'))
        v_target = sum(group.mapped('target_value'))
        cr.execute("SELECT COALESCE(SUM(quantity),0), COALESCE(SUM(value),0) "
                   "FROM stock_valuation_layer WHERE id IN %s", (inserted,))
        dq, dv = cr.fetchone()
        dq, dv = float(dq), float(dv)
        if abs(dq - (q_target - q0)) > 1e-3 or abs(dv - (v_target - v0)) > 1e-2:
            raise UserError(_(
                'void-and-reseed invariant failed for %s @ %s: inserted '
                'dq=%.4f dv=%.2f, expected %.4f / %.2f'
            ) % (product.display_name, warehouse.name, dq, dv,
                 q_target - q0, v_target - v0))

        if backup is not None:
            cr.execute("""
                INSERT INTO stock_count_adjustment_backup_line
                    (backup_id, layer_id, product_id, warehouse_id, quantity,
                     value, unit_cost, remaining_qty, remaining_value,
                     accounting_date, was_inserted,
                     create_uid, create_date, write_uid, write_date)
                SELECT %s, l.id, l.product_id, l.warehouse_id, l.quantity,
                       l.value, l.unit_cost, l.remaining_qty, l.remaining_value,
                       l.accounting_date, true,
                       %s, now() at time zone 'UTC', %s, now() at time zone 'UTC'
                FROM stock_valuation_layer l
                WHERE l.id IN %s
            """, (backup.id, uid, uid, inserted))
            if cr.rowcount != len(inserted):
                raise UserError(_(
                    'Backup incomplete: %s of %s inserted layers recorded.'
                ) % (cr.rowcount, len(inserted)))
            backup.invalidate_recordset(['line_ids'])

        return {'counter_id': counter_id, 'bucket_ids': bucket_ids,
                'zeroed_ids': zeroed_ids,
                'value_delta_reseed': v_target - v0,
                'qty_delta_reseed': q_target - q0}

    def _scoped_replay(self, group, reseed, cutoff_date):
        """Replay the FIFO engine over post-cutoff layers only, starting from
        the reseeded ending queue, and write back the repriced remaining_* /
        COGS values via raw SQL.

        Returns {'writes': int, 'cogs_writes': int, 'shortage': float,
                 'value_delta': float}.
        """
        SVL = self.env['stock.valuation.layer']
        product = group.product_id
        warehouse = group.warehouse_id
        company = group.adjustment_id.company_id
        utc_cutoff, _acct = self._cutoff_instants(cutoff_date)
        cr = self.env.cr

        SVL.flush_model(['quantity', 'value', 'remaining_qty', 'remaining_value',
                         'stock_landed_cost_id', 'stock_valuation_layer_id',
                         'create_date'])

        # Seed from the IMMUTABLE quantity / value, never remaining_* -- this
        # method must be idempotent. A second call (after _quant_adjust's
        # inventory move consumed from the buckets' remaining_*) re-seeds each
        # bucket to full quantity and rebuilds remaining_* by re-walking the
        # post-cutoff layers. Key by id, do NOT positionally zip bucket_ids.
        cr.execute("""
            SELECT id, quantity, value
            FROM stock_valuation_layer WHERE id IN %s
        """, (tuple(reseed['bucket_ids']),))
        seed_map = {r[0]: (float(r[1] or 0.0), float(r[2] or 0.0))
                    for r in cr.fetchall()}
        seed = [(bid, *seed_map[bid]) for bid in reseed['bucket_ids']]

        cr.execute("""
            SELECT id, quantity, value, stock_landed_cost_id, stock_valuation_layer_id
            FROM stock_valuation_layer
            WHERE product_id = %s AND warehouse_id = %s AND company_id = %s
              AND create_date > %s
            ORDER BY create_date, id
        """, (product.id, warehouse.id, company.id, utc_cutoff))
        rows = cr.fetchall()

        result = SVL._fifo_consume_rows(rows, seed=seed)
        if result['shortage'] > 1e-3:
            raise UserError(_(
                'FIFO shortage of %.4f units for %s @ %s after the cutoff — more '
                'was consumed than the target ending queue holds. Line aborted.'
            ) % (result['shortage'], product.display_name, warehouse.name))

        stored = SVL.browse(list(result['expected']))
        stored_map = {s.id: (s.remaining_qty, s.remaining_value) for s in stored}
        writes = 0
        value_delta = 0.0
        for layer_id, (nq, nv) in result['expected'].items():
            cq, cv = stored_map.get(layer_id, (0.0, 0.0))
            if abs(cq - nq) > 1e-4 or abs(cv - nv) > 1e-2:
                cr.execute("UPDATE stock_valuation_layer SET remaining_qty=%s, "
                           "remaining_value=%s WHERE id=%s", (nq, nv, layer_id))
                writes += 1
                value_delta += nv - cv

        cogs_writes = 0
        cogs_stored = SVL.browse(list(result['cogs']))
        cogs_map = {s.id: (s.value, s.quantity) for s in cogs_stored}
        for layer_id, new_value in result['cogs'].items():
            cur_value, qty = cogs_map.get(layer_id, (0.0, 0.0))
            if abs(cur_value - new_value) > 1e-2:
                uc = new_value / qty if qty else 0.0
                cr.execute("UPDATE stock_valuation_layer SET value=%s, unit_cost=%s "
                           "WHERE id=%s", (new_value, uc, layer_id))
                cogs_writes += 1

        SVL.invalidate_model(['remaining_qty', 'remaining_value', 'value', 'unit_cost'])
        return {'writes': writes, 'cogs_writes': cogs_writes,
                'shortage': result['shortage'], 'value_delta': value_delta}

    def _quant_adjust(self, group, cutoff_date, backup=None):
        """Step 5 -- align the pair's physical on-hand (stock.quant) with the
        move-history running balance, then neutralise the generated valuation
        layer (the value correction was already made by _void_and_reseed's
        bucket layers, so the inventory move must not double-count it).

        Target on-hand = the counted ending queue at the cutoff
        (sum of target_qty) walked forward through every post-cutoff `done`
        move-line that crosses the lot_stock_id subtree boundary. That is the
        quantity the quant *should* read today; if it already does (within
        Product Unit of Measure precision) this is a no-op.

        Returns {'move_id': int|False, 'svl_id': int|False, 'delta': float}.
        """
        product = group.product_id
        warehouse = group.warehouse_id
        company = group.adjustment_id.company_id
        lot_stock = warehouse.lot_stock_id
        utc_cutoff, _acct = self._cutoff_instants(cutoff_date)
        cr = self.env.cr
        uid = self.env.uid
        Quant = self.env['stock.quant']
        Move = self.env['stock.move']
        SVL = self.env['stock.valuation.layer']
        ML = self.env['stock.move.line']
        precision = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')

        child_ids = tuple(self.env['stock.location'].search(
            [('id', 'child_of', lot_stock.id)]).ids)

        # Net qty flow across the subtree boundary from post-cutoff done moves.
        ML.flush_model(['quantity', 'location_id', 'location_dest_id', 'date'])
        Move.flush_model(['state', 'date'])
        cr.execute("""
            SELECT COALESCE(SUM(
                CASE
                  WHEN sml.location_dest_id IN %(loc)s
                       AND sml.location_id NOT IN %(loc)s THEN sml.quantity
                  WHEN sml.location_id IN %(loc)s
                       AND sml.location_dest_id NOT IN %(loc)s THEN -sml.quantity
                  ELSE 0
                END), 0)
            FROM stock_move_line sml
            JOIN stock_move sm ON sm.id = sml.move_id
            WHERE sml.product_id = %(product)s AND sm.company_id = %(company)s
              AND sm.state = 'done' AND sml.date > %(cutoff)s
        """, {'loc': child_ids, 'product': product.id,
              'company': company.id, 'cutoff': utc_cutoff})
        post_flow = float(cr.fetchone()[0] or 0.0)

        target = sum(group.mapped('target_qty')) + post_flow

        Quant.flush_model(['quantity'])
        quants = Quant.search([
            ('product_id', '=', product.id),
            ('location_id', 'child_of', lot_stock.id),
            ('company_id', '=', company.id)])
        current = sum(quants.mapped('quantity'))

        if float_compare(target, current, precision_digits=precision) == 0:
            return {'move_id': False, 'svl_id': False, 'delta': 0.0}

        main = quants.filtered(lambda q: q.location_id.id == lot_stock.id)[:1] \
            or quants[:1]
        if not main:
            main = Quant.with_context(
                skip_warehouse_consistency_check=True).create({
                    'product_id': product.id,
                    'location_id': lot_stock.id,
                    'company_id': company.id,
                    'quantity': 0.0})
            # This quant was NOT in _touch_scope's snapshot (it did not exist
            # yet), so record its pre-image (quantity 0) now. Without this,
            # action_restore never resets it and a rollback leaves the phantom
            # on-hand _apply_inventory is about to write.
            if backup is not None:
                cr.execute("""
                    INSERT INTO stock_count_adjustment_backup_quant
                        (backup_id, quant_id, quantity,
                         create_uid, create_date, write_uid, write_date)
                    VALUES (%s, %s, %s,
                            %s, now() at time zone 'UTC', %s,
                            now() at time zone 'UTC')
                """, (backup.id, main.id, 0.0, uid, uid))
                backup.invalidate_recordset(['quant_line_ids'])
        # Put the whole discrepancy onto the main quant so the pair sum
        # lands exactly on `target`.
        main_target = target - (current - sum(main.mapped('quantity')))

        last_move_id = Move.search(
            [('company_id', '=', company.id)], order='id desc', limit=1).id or 0
        last_svl_id = SVL.search(
            [('company_id', '=', company.id)], order='id desc', limit=1).id or 0

        main.write({'inventory_quantity': main_target})
        main.with_context(
            skip_warehouse_consistency_check=True,
            inventory_date=fields.Date.to_date(cutoff_date))._apply_inventory()

        gen_moves = Move.search(
            [('company_id', '=', company.id), ('id', '>', last_move_id)])
        gen_mls = ML.search([('move_id', 'in', gen_moves.ids)]) \
            if gen_moves else ML.browse()
        gen_svls = SVL.search(
            [('company_id', '=', company.id), ('id', '>', last_svl_id)])
        move_id = gen_moves[:1].id if gen_moves else False
        svl_id = gen_svls[:1].id if gen_svls else False

        # Record the pre-image BEFORE the backdate UPDATEs -- restore deletes
        # these rows outright, but the as-generated snapshot keeps the backup
        # internally consistent.
        if backup is not None and gen_mls:
            ML.flush_model(['location_id', 'location_dest_id', 'date'])
            Move.flush_model(['date'])
            cr.execute("""
                INSERT INTO stock_count_adjustment_backup_moveline
                    (backup_id, move_line_id, move_id, location_id,
                     location_dest_id, ml_date, move_date, was_generated,
                     create_uid, create_date, write_uid, write_date)
                SELECT %s, sml.id, sml.move_id, sml.location_id,
                       sml.location_dest_id, sml.date, sm.date, true,
                       %s, now() at time zone 'UTC', %s, now() at time zone 'UTC'
                FROM stock_move_line sml
                JOIN stock_move sm ON sm.id = sml.move_id
                WHERE sml.id IN %s
            """, (backup.id, uid, uid, tuple(gen_mls.ids)))
            backup.invalidate_recordset(['moveline_line_ids'])
        if backup is not None and gen_svls:
            SVL.flush_model(['quantity', 'value', 'unit_cost', 'remaining_qty',
                             'remaining_value', 'accounting_date'])
            cr.execute("""
                INSERT INTO stock_count_adjustment_backup_line
                    (backup_id, layer_id, product_id, warehouse_id, quantity,
                     value, unit_cost, remaining_qty, remaining_value,
                     accounting_date, was_inserted,
                     create_uid, create_date, write_uid, write_date)
                SELECT %s, l.id, l.product_id, l.warehouse_id, l.quantity,
                       l.value, l.unit_cost, l.remaining_qty, l.remaining_value,
                       l.accounting_date, true,
                       %s, now() at time zone 'UTC', %s, now() at time zone 'UTC'
                FROM stock_valuation_layer l
                WHERE l.id IN %s
            """, (backup.id, uid, uid, tuple(gen_svls.ids)))
            backup.invalidate_recordset(['line_ids'])

        # Backdate the generated move / move lines, and fully neutralise the
        # generated valuation layer(s) so FIFO ignores them.
        Move.flush_model(['date'])
        ML.flush_model(['date'])
        SVL.flush_model(['quantity', 'value', 'unit_cost', 'remaining_qty',
                         'remaining_value', 'origin_remaining_qty',
                         'origin_remaining_value', 'create_date',
                         'accounting_date'])
        if gen_moves:
            cr.execute("UPDATE stock_move SET date = %s WHERE id IN %s",
                       (utc_cutoff, tuple(gen_moves.ids)))
            cr.execute("UPDATE stock_move_line SET date = %s WHERE move_id IN %s",
                       (utc_cutoff, tuple(gen_moves.ids)))
        if gen_svls:
            cr.execute("""
                UPDATE stock_valuation_layer
                SET quantity = 0, value = 0, remaining_qty = 0,
                    remaining_value = 0, unit_cost = 0,
                    origin_remaining_qty = 0, origin_remaining_value = 0,
                    create_date = %s, accounting_date = %s
                WHERE id IN %s
            """, (utc_cutoff, utc_cutoff, tuple(gen_svls.ids)))
        Move.invalidate_model()
        ML.invalidate_model()
        SVL.invalidate_model()

        return {'move_id': move_id, 'svl_id': svl_id,
                'delta': target - current}

    def _reconcile(self, group, cutoff_date):
        """SVL-vs-move reconciliation pass (step 6). DETECT + REPORT ONLY --
        writes nothing.

        For every post-cutoff SVL (create_date > the UTC cutoff instant) for
        this (product, warehouse) pair that carries a stock_move_id, compare
        the layer's booked quantity against the move's net quantity flow across
        the pair's lot_stock_id subtree boundary (sum of move-line `quantity`
        where location_dest_id is child_of lot_stock_id, minus where
        location_id is). If they disagree beyond UoM precision the move line's
        source / destination was corrupted after the layer was booked -- flag
        it for a manual fix.

        Returns list[dict] with keys matching stock.count.adjustment.mismatch
        fields so _write_engine_result / run() can Command.create them; [] when
        there are no post-cutoff stock_move_id layers or none disagree.
        """
        product = group.product_id
        warehouse = group.warehouse_id
        company = group.adjustment_id.company_id
        lot_stock = warehouse.lot_stock_id
        utc_cutoff, _acct = self._cutoff_instants(cutoff_date)
        rounding = product.uom_id.rounding
        cr = self.env.cr
        Move = self.env['stock.move']
        ML = self.env['stock.move.line']

        child_ids = tuple(self.env['stock.location'].search(
            [('id', 'child_of', lot_stock.id)]).ids)

        self.env['stock.valuation.layer'].flush_model(
            ['quantity', 'create_date'])
        ML.flush_model(['quantity', 'location_id', 'location_dest_id'])

        # strict `>` -- a layer created AT the cutoff instant (e.g. the
        # neutralised inventory layer _quant_adjust backdates to utc_cutoff) is
        # not a post-cutoff layer and must not be reconciled.
        cr.execute("""
            SELECT id, stock_move_id, quantity
            FROM stock_valuation_layer
            WHERE product_id = %s AND warehouse_id = %s AND company_id = %s
              AND create_date > %s AND stock_move_id IS NOT NULL
            ORDER BY create_date, id
        """, (product.id, warehouse.id, company.id, utc_cutoff))
        svl_rows = cr.fetchall()
        if not svl_rows:
            return []

        mismatches = []
        for svl_id, move_id, svl_qty in svl_rows:
            svl_qty = float(svl_qty or 0.0)
            cr.execute("""
                SELECT COALESCE(SUM(
                    (CASE WHEN location_dest_id IN %(loc)s
                          THEN quantity ELSE 0 END)
                  - (CASE WHEN location_id IN %(loc)s
                          THEN quantity ELSE 0 END)), 0)
                FROM stock_move_line
                WHERE move_id = %(move)s
            """, {'loc': child_ids or (0,), 'move': move_id})
            move_net_qty = float(cr.fetchone()[0] or 0.0)
            if float_compare(abs(svl_qty - move_net_qty), 0.0,
                             precision_rounding=rounding) <= 0:
                continue
            move = Move.browse(move_id)
            mls = ML.search([('move_id', '=', move_id)])
            suspect = mls.filtered(
                lambda l: l.location_id != move.location_id
                or l.location_dest_id != move.location_dest_id)[:1] or mls[:1]
            mismatches.append({
                'product_id': product.id,
                'warehouse_id': warehouse.id,
                'svl_id': svl_id,
                'move_id': move_id,
                'move_line_id': suspect.id or False,
                'svl_qty': svl_qty,
                'move_net_qty': move_net_qty,
                'diff': svl_qty - move_net_qty,
                'suggested_location_id': lot_stock.id,
            })
        return mismatches

    def _persist_mismatches(self, adjustment, result):
        """Replace adjustment.mismatch_ids from the run() result. Called from
        run() on a real (non-dry) run so callers that invoke run() directly
        still see the reconciliation report; action_apply's later
        _write_engine_result does the same and is harmless if repeated."""
        Mismatch = self.env['stock.count.adjustment.mismatch']
        adjustment.mismatch_ids.unlink()
        mvals = [dict(m, adjustment_id=adjustment.id)
                 for g in result.get('groups', [])
                 for m in g.get('mismatches', [])]
        if mvals:
            Mismatch.create(mvals)

    def run(self, adjustment, dry_run=True):
        """The void-reseed / scoped-replay / quant-adjust engine.

        The savepoint wraps BOTH paths; on a dry run `_DryRunRollback` unwinds
        it. `result` is a plain dict built inside the savepoint and returned to
        the caller, which writes it onto the records AFTER the savepoint has
        unwound -- so a preview survives its own rollback.
        """
        result = {'groups': [], 'valuation_delta': 0.0,
                  'cogs_delta': 0.0, 'qty_delta': 0.0, 'backup_id': False}
        backup = None
        try:
            with self.env.cr.savepoint():
                base = self._baseline(adjustment)
                if not dry_run:
                    scope = self._touch_scope(adjustment, base)
                    backup = self._snapshot(adjustment, scope)
                    result['backup_id'] = backup.id
                for group in adjustment._line_groups():
                    g = {'product_id': group.product_id.id,
                         'warehouse_id': group.warehouse_id.id,
                         'state': 'previewed', 'note': ''}
                    reason = self._check_category(
                        group.product_id, group.adjustment_id.company_id)
                    locked = self._locked_layer_count(group)
                    if reason or locked:
                        g['state'] = 'skipped'
                        g['note'] = reason or _('%s locked layers') % locked
                        result['groups'].append(g)
                        continue
                    gl_backed = self._gl_backed_layer_count(
                        group, adjustment.cutoff_date)
                    if gl_backed:
                        # No writes -- guard sits before _void_and_reseed.
                        g['state'] = 'error'
                        g['note'] = _(
                            '%s post-cutoff layers carry journal entries — GL '
                            'reposting is out of scope') % gl_backed
                        result['groups'].append(g)
                        continue
                    rounding = group.product_id.uom_id.rounding
                    target_sum = sum(group.mapped('target_qty'))
                    negative_target = float_compare(
                        target_sum, 0.0, precision_rounding=rounding) < 0
                    if negative_target:
                        # Spec §8: a negative target sum is explicitly allowed
                        # (the counter layer can exceed on-hand) -- warn only.
                        # An error in the try-block below still supersedes this.
                        g['note'] = _('Target qty sums to %.2f (negative)') % (
                            target_sum,)
                    else:
                        reserved = self._reserved_qty(group)
                        if float_compare(reserved, target_sum,
                                         precision_rounding=rounding) > 0:
                            # No writes for this group -- guard sits before
                            # _void_and_reseed so nothing is half-applied.
                            g['state'] = 'error'
                            g['note'] = _(
                                'Reserved qty %.2f exceeds target %.2f') % (
                                reserved, target_sum)
                            result['groups'].append(g)
                            continue
                    q0, v0 = base[(g['product_id'], g['warehouse_id'])]
                    try:
                        reseed = self._void_and_reseed(
                            group, q0, v0, adjustment.cutoff_date, backup=backup)
                        r1 = self._scoped_replay(
                            group, reseed, adjustment.cutoff_date)
                        qa = self._quant_adjust(
                            group, adjustment.cutoff_date, backup=backup)
                        if qa['delta']:
                            # The inventory move consumed from the bucket
                            # remaining_* queue; re-walk to restore it (the
                            # neutralised, qty-0 inventory SVL contributes
                            # nothing).
                            r1 = self._scoped_replay(
                                group, reseed, adjustment.cutoff_date)
                        g['mismatches'] = self._reconcile(
                            group, adjustment.cutoff_date)
                        g['baseline'] = (q0, v0)
                        # The dominant term is the reseed delta (v_target - v0);
                        # _scoped_replay only adds the post-cutoff remaining-value
                        # drift on top. Reporting r1 alone under-counts grossly.
                        g['value_delta'] = (reseed['value_delta_reseed']
                                            + r1['value_delta'])
                        g['qty_delta'] = reseed['qty_delta_reseed']
                        g['quant_delta'] = qa['delta']
                        result['valuation_delta'] += g['value_delta']
                        result['qty_delta'] += g['qty_delta']
                    except UserError as e:
                        g['state'] = 'error'
                        # keep any pre-try warning (e.g. negative target sum)
                        g['note'] = (g['note'] + ' | ' if g['note']
                                     else '') + str(e)
                    result['groups'].append(g)
                if dry_run:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        # The savepoint rolled the DB back but the ORM cache still holds the
        # voided / reseeded values and ids of rows that no longer exist.
        self.env.invalidate_all()
        if not dry_run:
            self._persist_mismatches(adjustment, result)
        return result
