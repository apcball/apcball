# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime

class BuzSaleOrderReport(models.Model):
    _name = 'buz.sale.order.report'
    _description = 'Custom Sale Order Report'

    # Report fields
    name = fields.Char(string='Report Name')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order Reference')
    lang_version = fields.Selection([
        ('th', 'Thai'),
        ('en', 'English')
    ], string='Language Version', default='th')

class SaleOrderReportTemplate(models.AbstractModel):
    _name = 'report.buz_sale_order_report.report_sale_order'
    _description = 'Sale Order Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['sale.order'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'sale.order',
            'docs': docs,
            'data': data,
        }