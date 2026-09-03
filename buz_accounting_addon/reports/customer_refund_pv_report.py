# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError, AccessError

class CustomerRefundPVReport(models.AbstractModel):
    _name = 'report.buz_accounting_addon.report_customer_refund_pv'
    _description = 'Customer Refund PV Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['buz.customer.refund.voucher'].browse(docids)
        for doc in docs:
            # access check
            doc.check_access_rights('read')
            doc.check_access_rule('read')
            if doc.workflow_state not in ('confirmed', 'in_payment', 'partially_refunded', 'paid'):
                raise UserError(_("Printing not allowed for state %s") % doc.workflow_state)
            # company check
            if doc.company_id not in self.env.companies and not self.env.su:
                raise AccessError(_("Access denied for company"))
        return {
            'doc_ids': docids,
            'doc_model': 'buz.customer.refund.voucher',
            'docs': docs,
            'data': data,
        }
