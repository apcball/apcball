from datetime import datetime, time, timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

# Thailand has no DST, so Bangkok is always a fixed UTC+7 offset.
BANGKOK_OFFSET = timedelta(hours=7)


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

    def _check_category(self, product):
        """Reason string when the product's category posts real-time journal
        entries (GL reposting is out of scope for v1), else False."""
        if product.categ_id.property_valuation == 'real_time':
            return _('Product category %s posts real-time journal entries; '
                     'GL reposting is out of scope for v1.') % product.categ_id.name
        return False

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
        rows = Report.search_read(
            [('product_id', 'in', product_ids),
             ('warehouse_id', 'in', warehouse_ids)],
            ['product_id', 'warehouse_id', 'ending_qty', 'ending_value'])
        base = {(r['product_id'][0], r['warehouse_id'][0]):
                (r['ending_qty'], r['ending_value']) for r in rows}
        return {pair: base.get(pair, (0.0, 0.0)) for pair in pairs}

    def _void_and_reseed(self, group, q0, v0, cutoff_date):
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

        return {'counter_id': counter_id, 'bucket_ids': bucket_ids,
                'zeroed_ids': zeroed_ids}

    def run(self, adjustment, dry_run=True):
        """The 6-step void-reseed / scoped-replay engine. Filled in Tasks 4-9."""
        return {}
