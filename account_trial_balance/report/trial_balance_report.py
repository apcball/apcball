# -*- coding: utf-8 -*-
from odoo import api, models


class TrialBalanceReport(models.AbstractModel):
    _name = 'report.account_trial_balance.report_trial_balance_document'
    _description = 'Trial Balance PDF Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not docids and data and data.get('ids'):
            docids = data['ids']
            
        docs = self.env['account.trial.balance.wizard'].browse(docids)
        
        # If wizard record is already garbage collected, we might need to recreate a mock one
        # but typically the IDs are still valid during the same request.
        
        def format_number(value, digits=2):
            return "{:,.2f}".format(value)
        
        return {
            'doc_ids': docids,
            'doc_model': 'account.trial.balance.wizard',
            'docs': docs,
            'data': data or {},
            'formatLang': format_number,
        }