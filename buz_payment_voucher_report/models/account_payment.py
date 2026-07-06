# -*- coding: utf-8 -*-
"""
Account Payment Extension

Adds smart button to print Payment Voucher directly from account.payment form view.
"""
from odoo import models, _


class AccountPayment(models.Model):
    """
    Extend account.payment with print Payment Voucher functionality.

    The smart button on the form view calls this method to generate
    a PDF Payment Voucher for the current payment.
    """
    _inherit = 'account.payment'

    def action_print_payment_voucher(self):
        """
        Print Payment Voucher PDF for the current payment.

        Uses report_action to generate the PDF using the QWeb template.

        :return: Report action for PDF download
        :rtype: dict
        """
        self.ensure_one()
        return self.env.ref(
            'buz_payment_voucher_report.action_report_payment_voucher'
        ).report_action(self)

    def _get_reconciled_invoices(self):
        """
        Get invoices/bills reconciled with this payment.

        Iterates through move lines matched debit/credit relations
        to find reconciled account.move records.

        :return: recordset of account.move (invoices/bills)
        :rtype: account.move recordset
        """
        self.ensure_one()
        if not self.move_id:
            return self.env['account.move']
        matched_moves = self.env['account.move']
        for line in self.move_id.line_ids:
            for matched in line.matched_debit_ids:
                matched_moves |= matched.credit_move_id.move_id
            for matched in line.matched_credit_ids:
                matched_moves |= matched.debit_move_id.move_id
        return matched_moves
