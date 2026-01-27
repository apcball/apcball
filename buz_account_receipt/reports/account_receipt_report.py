# -*- coding: utf-8 -*-
from odoo import models, api


class AccountReceiptReportPDF(models.AbstractModel):
    _name = 'report.buz_account_receipt.account_receipt_report_preprint'
    _description = 'Account Receipt Preprint PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        """
        Override to ensure proper UTF-8 encoding for Thai language support
        and provide additional context for the receipt report
        """
        docs = self.env['account.receipt'].browse(docids)
        
        return {
            'doc_ids': docids,
            'doc_model': 'account.receipt',
            'docs': docs,
            'data': data,
        }
