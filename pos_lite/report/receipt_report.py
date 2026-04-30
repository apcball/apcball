# -*- coding: utf-8 -*-
from odoo import api, models


class ReportPosLiteReceipt(models.AbstractModel):
    _name = 'report.pos_lite.report_receipt_document'
    _description = 'POS Lite Receipt Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['pos.lite.order'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'pos.lite.order',
            'docs': docs,
            'data': data or {},
        }
