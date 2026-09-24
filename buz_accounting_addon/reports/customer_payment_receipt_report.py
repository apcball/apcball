# -*- coding: utf-8 -*-
"""Report context and validation for Customer Receipt Voucher."""
from odoo import api, fields, models
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

        def format_thai_date(value):
            """Format a date as DD/MM/YYYY using the Buddhist calendar."""
            if not value:
                return "-"
            date_value = fields.Date.to_date(value)
            return date_value.strftime("%d/%m/") + str(date_value.year + 543)

        invalid = payments.filtered(
            lambda payment: payment.partner_type != "customer"
            or payment.payment_type not in ("inbound", "receive")
        )
        if invalid:
            raise UserError(
                "Receipt Voucher ใช้ได้เฉพาะ Customer / Receive (Inbound) Payment เท่านั้น"
            )

        receipt_rows = {}
        payment_rows = {}
        journal_rows = {}
        for payment in payments:
            receipt_rows[payment.id] = [{
                "partner_code": getattr(payment.partner_id, "partner_code", False) or "-",
                "partner_name": payment.partner_id.name or "-",
                "document": "ใบเสร็จรับเงิน",
                "document_number": payment.name or "-",
                "date": format_thai_date(payment.date),
                "amount": payment.amount or 0.0,
            }]

            payment_rows[payment.id] = [{
                "method": dict(payment._fields["buz_payment_channel"].selection).get(payment.buz_payment_channel, "-") if payment.buz_payment_channel else "-",
                "journal": payment.journal_id.name or "-",
                "check_number": getattr(payment, "check_number", False) or "-",
                "date": format_thai_date(payment.received_date or payment.date),
                "amount": payment.amount or 0.0,
            }]

            move = payment.move_id
            journal_rows[payment.id] = [
                {
                    "code": line.account_id.code or "-",
                    "name": line.account_id.name or "-",
                    "ref": payment.name or move.name or move.ref or "-",
                    "date": format_thai_date(payment.date),
                    "debit": line.debit or 0.0,
                    "credit": line.credit or 0.0,
                }
                for line in move.line_ids
            ] if move else []

        return {
            "doc_ids": docids,
            "doc_model": "account.payment",
            "docs": payments,
            "data": data,
            "receipt_rows": receipt_rows,
            "payment_rows": payment_rows,
            "journal_rows": journal_rows,
            "format_amount": format_amount,
            "format_thai_date": format_thai_date,
        }