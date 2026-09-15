# -*- coding: utf-8 -*-
"""Report context and validation for Customer Receipt Voucher."""
from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class CustomerPaymentReceiptReport(models.AbstractModel):
    _name = "report.buz_accounting_addon.customer_payment_receipt"
    _description = "Customer Payment Receipt Voucher PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        payments = self.env["account.payment"].browse(docids).exists()

        def format_amount(amount, currency):
            """Format a monetary value for the QWeb report."""
            return formatLang(
                self.env,
                amount or 0.0,
                currency_obj=currency,
            )
        invalid = payments.filtered(
            lambda payment: payment.partner_type != "customer"
            or payment.payment_type not in ("inbound", "receive")
        )
        if invalid:
            raise UserError(
                "Receipt Voucher ใช้ได้เฉพาะ Customer / Receive (Inbound) Payment เท่านั้น"
            )

        invoice_rows = {}
        payment_rows = {}
        journal_rows = {}
        for payment in payments:
            invoices = getattr(payment, "reconciled_invoice_ids", self.env["account.move"])
            invoice_rows[payment.id] = [
                {"name": invoice.name or "-", "date": invoice.invoice_date,
                 "amount": invoice.amount_total}
                for invoice in invoices
            ]
            check_number = getattr(payment, "check_number", False) or "-"
            payment_rows[payment.id] = [{
                "method": "Cheque" if check_number != "-" else (payment.payment_method_line_id.name or "-"),
                "journal": payment.journal_id.name or "-",
                "check_number": check_number,
                "date": payment.date,
                "amount": payment.amount,
            }]
            move = payment.move_id
            journal_rows[payment.id] = [
                {"code": line.account_id.code or "-", "name": line.account_id.name or "-",
                 "ref": line.name or move.ref or "-", "date": line.date or move.date,
                 "debit": line.debit, "credit": line.credit}
                for line in move.line_ids
            ] if move else []
        return {
            "doc_ids": docids, "doc_model": "account.payment", "docs": payments,
            "data": data, "invoice_rows": invoice_rows, "payment_rows": payment_rows,
            "journal_rows": journal_rows,
            # A custom report does not receive this helper automatically.
            "format_amount": format_amount,
        }