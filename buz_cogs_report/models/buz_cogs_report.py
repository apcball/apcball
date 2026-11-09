# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo import fields, models, tools


class BuzCogsReport(models.Model):
    _name = 'buz.cogs.report'
    _description = 'Actual COGS Report'
    _auto = False
    _order = 'acct_date desc, id desc'

    acct_date = fields.Date(string='Accounting Date', readonly=True)
    acct_month = fields.Char(string='Month', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    product_categ_id = fields.Many2one('product.category', string='Product Category', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    stock_move_id = fields.Many2one('stock.move', string='Stock Move', readonly=True)
    picking_id = fields.Many2one('stock.picking', string='Transfer', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    dispatch_document_name = fields.Char(string='Dispatch Document (DP)', readonly=True)
    kind = fields.Selection(
        [('sale', 'Sale (to customer)'),
         ('return', 'Customer Return'),
         ('other_out', 'Other Out (transfer/MO/scrap/...)'),
         ('other_in', 'Other In'),
         ('landed_cost', 'Landed Cost'),
         ('reval', 'Revaluation / No-qty')],
        readonly=True)
    quantity = fields.Float(string='Qty (SVL, signed)', readonly=True)
    value = fields.Monetary(
        string='SVL Value (signed)', readonly=True, currency_field='currency_id',
        help='Raw stock.valuation.layer value. Sum by kind reconciles to the '
             'FIFO report: out_value = sum(value) of sale+other_out, '
             'in_value = return+other_in.')
    cogs = fields.Monetary(
        string='COGS', readonly=True, currency_field='currency_id',
        help='-value for Sale and Customer Return layers, else 0.')
    default_code = fields.Char(string='Product Code', readonly=True)
    product_name = fields.Char(string='Product Name', readonly=True)
    doc_no = fields.Char(string='Document No', readonly=True,
                         help='Dispatch document (DP) if any, else the transfer name.')
    qt = fields.Float(string='Qty Sold', readonly=True)
    cost = fields.Monetary(string='Cost', readonly=True, currency_field='currency_id')
    qt_return = fields.Float(string='Qty Return', readonly=True)
    cost_return = fields.Monetary(string='Cost Return', readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Same window as stock_fifo_valuation_report: acct_date >= cutoff (Bangkok
        # midnight expressed in UTC). Re-run init (module update) if the param changes.
        cutoff = self.env['ir.config_parameter'].sudo().get_param(
            'stock_fifo_valuation_report.cutoff_date')
        utc_lower = (fields.Datetime.to_datetime(cutoff) - timedelta(hours=7)
                     if cutoff else datetime(1900, 1, 1))
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    svl.id AS id,
                    (COALESCE(svl.accounting_date, svl.create_date)
                        AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Bangkok')::date AS acct_date,
                    to_char((COALESCE(svl.accounting_date, svl.create_date)
                        AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Bangkok'), 'YYYY-MM') AS acct_month,
                    svl.product_id,
                    tmpl.categ_id AS product_categ_id,
                    svl.warehouse_id,
                    svl.company_id,
                    svl.stock_move_id,
                    sm.picking_id,
                    sp.partner_id,
                    dp.names AS dispatch_document_name,
                    CASE
                        WHEN svl.quantity < 0 AND ld.usage = 'customer' AND ls.usage <> 'customer' THEN 'sale'
                        WHEN svl.quantity > 0 AND ls.usage = 'customer' AND ld.usage <> 'customer' THEN 'return'
                        WHEN svl.quantity < 0 THEN 'other_out'
                        WHEN svl.quantity > 0 THEN 'other_in'
                        WHEN svl.stock_landed_cost_id IS NOT NULL THEN 'landed_cost'
                        ELSE 'reval'
                    END AS kind,
                    svl.quantity AS quantity,
                    svl.value AS value,
                    CASE
                        WHEN svl.quantity < 0 AND ld.usage = 'customer' AND ls.usage <> 'customer' THEN -svl.value
                        WHEN svl.quantity > 0 AND ls.usage = 'customer' AND ld.usage <> 'customer' THEN -svl.value
                        ELSE 0
                    END AS cogs,
                    pp.default_code AS default_code,
                    COALESCE(tmpl.name->>'en_US', tmpl.name->>'th_TH') AS product_name,
                    COALESCE(dp.names, sp.name) AS doc_no,
                    CASE WHEN svl.quantity < 0 AND ld.usage = 'customer' AND ls.usage <> 'customer'
                         THEN -svl.quantity ELSE 0 END AS qt,
                    CASE WHEN svl.quantity < 0 AND ld.usage = 'customer' AND ls.usage <> 'customer'
                         THEN -svl.value ELSE 0 END AS cost,
                    CASE WHEN svl.quantity > 0 AND ls.usage = 'customer' AND ld.usage <> 'customer'
                         THEN svl.quantity ELSE 0 END AS qt_return,
                    CASE WHEN svl.quantity > 0 AND ls.usage = 'customer' AND ld.usage <> 'customer'
                         THEN svl.value ELSE 0 END AS cost_return,
                    comp.currency_id
                FROM stock_valuation_layer svl
                JOIN product_product pp ON pp.id = svl.product_id
                JOIN product_template tmpl ON tmpl.id = pp.product_tmpl_id
                JOIN res_company comp ON comp.id = svl.company_id
                LEFT JOIN stock_move sm ON sm.id = svl.stock_move_id
                LEFT JOIN stock_location ld ON ld.id = sm.location_dest_id
                LEFT JOIN stock_location ls ON ls.id = sm.location_id
                LEFT JOIN stock_picking sp ON sp.id = sm.picking_id
                LEFT JOIN (
                    SELECT stock_picking_id, string_agg(name, ', ' ORDER BY name) AS names
                    FROM buz_dispatch_document
                    WHERE name IS NOT NULL
                    GROUP BY stock_picking_id
                ) dp ON dp.stock_picking_id = sm.picking_id
                WHERE COALESCE(svl.accounting_date, svl.create_date) >= %%s
            )
        """ % self._table, (utc_lower,))
