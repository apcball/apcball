# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .res_config_settings import get_plan_config

# History below this is not a real lead time (MOs are mostly closed the day
# they start), so the Settings default is used instead.
MIN_USABLE_MAKE_LEAD_DAYS = 0.5


class PlanProductParam(models.Model):
    _name = 'buz.plan.product.param'
    _description = 'Product Planning Parameters'
    _inherit = ['mail.thread']
    _check_company_auto = True
    _rec_name = 'product_id'
    _order = 'product_id'

    product_id = fields.Many2one(
        'product.product', required=True, index=True, ondelete='cascade',
        domain=[('detailed_type', '=', 'product')], check_company=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    safety_stock = fields.Float(digits='Product Unit of Measure', tracking=True)
    min_batch_qty = fields.Float(string="Minimum Batch Qty", digits='Product Unit of Measure')
    batch_multiple = fields.Float(digits='Product Unit of Measure')
    lead_time_make_days = fields.Float(string="Manufacturing Lead Time (days)")
    lead_time_buy_days = fields.Float(string="Purchase Lead Time (days)")
    supply_method = fields.Selection([
        ('auto', "Automatic (BoM → make, else buy)"),
        ('make', "Make"),
        ('buy', "Buy"),
        ('none', "Do not plan"),
    ], default='auto', required=True, tracking=True)
    picking_type_id = fields.Many2one(
        'stock.picking.type', string="Production Line", check_company=True,
        domain=[('code', '=', 'mrp_operation')])
    vendor_id = fields.Many2one(
        'res.partner', string="Vendor Override", domain=[('supplier_rank', '>', 0)])
    forecast_method = fields.Selection([
        ('avg', "Average of past deliveries"),
        ('manual', "Manual"),
        ('none', "None"),
    ], default='avg', required=True)

    _sql_constraints = [
        ('product_company_uniq', 'unique(product_id, company_id)',
         "Planning parameters already exist for this product in this company."),
        ('safety_stock_positive', 'check(safety_stock >= 0)', "Safety stock cannot be negative."),
        ('min_batch_positive', 'check(min_batch_qty >= 0)', "Minimum batch qty cannot be negative."),
        ('batch_multiple_positive', 'check(batch_multiple >= 0)', "Batch multiple cannot be negative."),
    ]

    def action_compute_defaults(self):
        """Fill lead times, production line and minimum batch from history.

        Works on the selected records (batch SQL, one query per metric).
        Products without history receive the defaults from Settings.
        """
        if not self:
            raise UserError(_("Select at least one product parameter line."))
        cfg = get_plan_config(self.env)
        cutoff = cfg['history_cutoff']
        product_ids = self.product_id.ids
        company_ids = self.company_id.ids
        make = self._history_make(product_ids, company_ids, cutoff)
        buy = self._history_buy(product_ids, company_ids, cutoff)
        for rec in self:
            key = (rec.product_id.id, rec.company_id.id)
            m = make.get(key)
            b = buy.get(key)
            vals = {
                'lead_time_make_days': (
                    m['lead_days'] if m and m['lead_days'] >= MIN_USABLE_MAKE_LEAD_DAYS
                    else cfg['lead_make_days']),
                'lead_time_buy_days': b if b is not None else cfg['lead_buy_days'],
            }
            if m:
                vals['min_batch_qty'] = m['median_qty']
                vals['picking_type_id'] = m['picking_type_id']
            rec.write(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Defaults computed"),
                'message': _("%(n)s line(s) updated from history since %(d)s.",
                             n=len(self), d=cutoff),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def _history_make(self, product_ids, company_ids, cutoff):
        """Median lead time/size and latest line per product from done MOs."""
        self.env.cr.execute("""
            SELECT mo.product_id, mo.company_id,
                   percentile_cont(0.5) WITHIN GROUP (
                       ORDER BY EXTRACT(EPOCH FROM (mo.date_finished - mo.date_start)) / 86400.0
                   ) FILTER (
                       WHERE mo.date_finished > mo.date_start
                         AND mo.date_finished - mo.date_start < interval '60 days'
                   ) AS lead_days,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY mo.product_qty) AS median_qty,
                   (ARRAY_AGG(mo.picking_type_id ORDER BY mo.date_finished DESC, mo.id DESC))[1]
                       AS picking_type_id
              FROM mrp_production mo
             WHERE mo.state = 'done'
               AND mo.date_finished >= %s
               AND mo.product_id = ANY(%s)
               AND mo.company_id = ANY(%s)
             GROUP BY mo.product_id, mo.company_id
        """, (cutoff, list(product_ids), list(company_ids)))
        return {
            (r[0], r[1]): {
                'lead_days': round(r[2], 1) if r[2] is not None else 0.0,
                'median_qty': r[3] or 0.0,
                'picking_type_id': r[4],
            } for r in self.env.cr.fetchall()
        }

    @api.model
    def _history_buy(self, product_ids, company_ids, cutoff):
        """Median days from PO approval to the received move, per product."""
        self.env.cr.execute("""
            SELECT sm.product_id, po.company_id,
                   percentile_cont(0.5) WITHIN GROUP (
                       ORDER BY EXTRACT(EPOCH FROM (sm.date - po.date_approve)) / 86400.0)
              FROM stock_move sm
              JOIN purchase_order_line pol ON pol.id = sm.purchase_line_id
              JOIN purchase_order po ON po.id = pol.order_id
             WHERE sm.state = 'done'
               AND po.date_approve IS NOT NULL
               AND sm.date > po.date_approve
               AND sm.date - po.date_approve < interval '180 days'
               AND po.date_approve >= %s
               AND sm.product_id = ANY(%s)
               AND po.company_id = ANY(%s)
             GROUP BY sm.product_id, po.company_id
        """, (cutoff, list(product_ids), list(company_ids)))
        return {(r[0], r[1]): round(r[2], 1) for r in self.env.cr.fetchall()}
