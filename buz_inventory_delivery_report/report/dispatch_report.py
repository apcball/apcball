# -*- coding: utf-8 -*-
from odoo import models, api


class DispatchReportPDF(models.AbstractModel):
    _name = 'report.buz_inventory_delivery_report.dispatch_report_document'
    _description = 'Dispatch Report PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        """
        Override to ensure proper UTF-8 encoding for Thai language support
        """
        docs = self.env['stock.picking'].browse(docids)
        
        return {
            'doc_ids': docids,
            'doc_model': 'stock.picking',
            'docs': docs,
            'data': data,
        }
