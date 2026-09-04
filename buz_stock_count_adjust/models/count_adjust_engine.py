from datetime import datetime, time, timedelta

from odoo import _, fields, models

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

    def run(self, adjustment, dry_run=True):
        """The 6-step void-reseed / scoped-replay engine. Filled in Tasks 4-9."""
        return {}
