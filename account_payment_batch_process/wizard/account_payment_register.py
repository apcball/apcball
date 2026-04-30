# Copyright (C) 2021, Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)

try:
    from num2words import num2words
except ImportError:
    _logger.warning(
        "The num2words python library is not installed."
    )
    num2words = None


MAP_INVOICE_TYPE_PARTNER_TYPE = {
    "out_invoice": "customer",
    "out_refund": "customer",
    "in_invoice": "supplier",
    "in_refund": "supplier",
}

# Since invoice amounts are unsigned,
# this is how we know if money comes in or goes out
MAP_INVOICE_TYPE_PAYMENT_SIGN = {
    "out_invoice": 1,
    "in_refund": 1,
    "in_invoice": -1,
    "out_refund": -1,
}


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    @api.depends("invoice_payments.amount")
    def _compute_total(self):
        self.total_amount = sum(line.amount for line in self.invoice_payments)

    @api.depends("invoice_payments.amount")
    def _compute_cheque_amount(self):
        """Auto-sync cheque_amount with total pay amount so user can
        edit line amounts directly without needing to adjust cheque_amount."""
        self.cheque_amount = sum(line.amount for line in self.invoice_payments)

    is_auto_fill = fields.Char(string="Auto-Fill Pay Amount")
    invoice_payments = fields.One2many(
        "invoice.payment.line", "wizard_id", string="Payments"
    )
    is_customer = fields.Boolean(string="Is Customer?")
    cheque_amount = fields.Float(
        "Batch Payment Total",
        required=True,
        compute="_compute_cheque_amount",
        store=True,
        readonly=False,
    )
    total_amount = fields.Float("Total Invoices:", compute="_compute_total")

    def get_invoice_payment_line(self, invoice):
        return (
            0,
            0,
            {
                "partner_id": invoice.partner_id.id,
                "invoice_id": invoice.id,
                "balance": invoice.amount_residual or 0.0,
                "amount": invoice.amount_residual or 0.0,
                "payment_difference": 0.0,
                "payment_difference_handling": "open",
                "note": "Payment of invoice %s" % invoice.name,
            },
        )

    def get_invoice_payments(self, invoices):
        res = []
        for invoice in invoices:
            res.append(self.get_invoice_payment_line(invoice))
        return res

    def _invoice_payments_are_default(self):
        """Detect whether the batch lines still mirror invoice residuals."""
        self.ensure_one()
        if not self.invoice_payments:
            return False

        rounding = self.currency_id.rounding or self.company_id.currency_id.rounding
        return all(
            float_compare(line.amount, line.balance, precision_rounding=rounding) == 0
            for line in self.invoice_payments
        )

    def _fill_invoice_payments_from_batch_amount(self, remaining_amount, persist=False):
        """Allocate the batch total sequentially across invoice lines."""
        self.ensure_one()
        total = 0.0
        for payline in self.invoice_payments:
            if remaining_amount <= 0.0:
                amount = 0.0
            else:
                amount = min(remaining_amount, payline.balance)
            remaining_amount -= amount
            total += amount

            values = {
                "amount": amount,
                "payment_difference": payline.balance - amount,
                "payment_difference_handling": "open",
            }
            if persist:
                payline.write(values)
            else:
                payline.amount = amount
                payline.payment_difference = values["payment_difference"]
                payline.payment_difference_handling = values[
                    "payment_difference_handling"
                ]

        self.amount = total
        self.cheque_amount = total
        return total

    def _get_batch_payment_amount(self):
        """Pick the amount the user actually intended to pay.

        The standard wizard amount is the primary input the user edits in the
        UI. We still keep cheque_amount in sync for convenience, but if one of
        them differs from the invoice total we use that value to allocate the
        batch.
        """
        self.ensure_one()
        rounding = self.currency_id.rounding or self.company_id.currency_id.rounding
        if float_compare(self.amount, self.total_amount, precision_rounding=rounding) != 0:
            return self.amount
        if float_compare(
            self.cheque_amount, self.total_amount, precision_rounding=rounding
        ) != 0:
            return self.cheque_amount
        return self.total_amount

    @api.model
    def default_get(self, fields_list):
        if self.env.context and not self.env.context.get("batch", False):
            return super().default_get(fields_list)
        res = super().default_get(fields_list)
        context = dict(self._context or {})
        active_model = context.get("active_model")
        active_ids = context.get("active_ids")
        # Checks on context parameters
        if not active_model or not active_ids:
            raise UserError(
                _(
                    "The wizard is executed without active_model or active_ids in the context."
                )
            )
        if active_model != "account.move":
            raise UserError(
                _("The expected model for this action is 'account.move', not '%s'.")
                % active_model
            )
        # Checks on received invoice records
        invoices = self.env[active_model].browse(active_ids)
        if any(
            invoice.state != "posted"
            or invoice.payment_state not in ["not_paid", "partial"]
            for invoice in invoices
        ):
            raise UserError(_("You can only register payments for posted invoices."))

        if any(
            MAP_INVOICE_TYPE_PARTNER_TYPE[inv.move_type]
            != MAP_INVOICE_TYPE_PARTNER_TYPE[invoices[0].move_type]
            for inv in invoices
        ):
            raise UserError(
                _(
                    "You cannot mix customer invoices and vendor bills in a single payment."
                )
            )
        if any(inv.currency_id != invoices[0].currency_id for inv in invoices):
            raise UserError(
                _(
                    "In order to pay multiple bills at once, they must use the same currency."
                )
            )

        if "batch" in context and context.get("batch"):
            is_customer = (
                MAP_INVOICE_TYPE_PARTNER_TYPE[invoices[0].move_type] == "customer"
            )
            payment_lines = self.get_invoice_payments(invoices)
            res.update({"invoice_payments": payment_lines, "is_customer": is_customer})

        total_amount = sum(
            inv.amount_residual * MAP_INVOICE_TYPE_PAYMENT_SIGN[inv.move_type]
            for inv in invoices
        )
        date_format = self.env["res.lang"]._lang_get(self.env.user.lang).date_format
        communication = "Batch payment of %s" % fields.Date.today().strftime(
            date_format
        )
        res.update(
            {
                "amount": abs(total_amount),
                "currency_id": invoices[0].currency_id.id,
                "payment_type": "outbound" if is_customer else "inbound",
                "partner_id": invoices[0].commercial_partner_id.id,
                "partner_type": MAP_INVOICE_TYPE_PARTNER_TYPE[invoices[0].move_type],
                "company_id": self.env.company.id,
                "communication": communication,
            }
        )
        return res

    def get_payment_values(self, group_data=None):
        if not group_data:
            return {}

        # Resolve destination account from the first invoice
        destination_account_id = False
        invoice_ids = list(group_data.get("inv_val", {}))
        if invoice_ids:
            first_invoice = self.env["account.move"].browse(invoice_ids[0])
            dest_accounts = first_invoice.line_ids.filtered(
                lambda l: l.account_id.account_type in (
                    "asset_receivable", "liability_payable"
                )
            ).mapped("account_id")
            if dest_accounts:
                destination_account_id = dest_accounts[0].id

        res = {
            "journal_id": self.journal_id.id,
            "payment_method_line_id": "payment_method_line_id" in group_data
            and group_data["payment_method_line_id"]
            or self.payment_method_line_id.id,
            "date": self.payment_date,
            "payment_type": self.payment_type,
            "amount": group_data["total"],
            "currency_id": self.currency_id.id,
            "partner_bank_id": self.partner_bank_id.id,
            "partner_id": int(group_data["partner_id"]),
            "partner_type": group_data["partner_type"],
            "ref": group_data["check_amount_in_words"],
            "write_off_line_vals": [],
        }
        # Set destination account to ensure correct receivable/payable matching
        if destination_account_id:
            res["destination_account_id"] = destination_account_id

        # Integration with sr_extra_bank_charges:
        # Pass bank charge values to the created payment if the fields exist.
        if 'bank_charge_amount' in self._fields:
            res['bank_charge_amount'] = self.bank_charge_amount
            res['bank_charge_currency_id'] = self.bank_charge_currency_id.id

        conversion_rate = self.env["res.currency"]._get_conversion_rate(
            self.currency_id,
            self.company_id.currency_id,
            self.company_id,
            self.payment_date,
        )
        for invoice_id in list(group_data["inv_val"]):
            values = group_data["inv_val"][invoice_id]
            if (
                self.currency_id
                and not self.currency_id.is_zero(values["payment_difference"])
                and values["payment_difference_handling"] == "reconcile"
            ):
                writeoff_name = values.get("line_name", False)
                writeoff_account_id = values.get("writeoff_account_id", False)
                if self.payment_type == "inbound":
                    write_off_amount_currency = values["payment_difference"]
                else:
                    write_off_amount_currency = -values["payment_difference"]
                write_off_balance = self.company_id.currency_id.round(
                    write_off_amount_currency * conversion_rate
                )
                res["write_off_line_vals"].append(
                    {
                        "name": writeoff_name,
                        "account_id": writeoff_account_id,
                        "partner_id": self.partner_id.id,
                        "currency_id": self.currency_id.id,
                        "amount_currency": write_off_amount_currency,
                        "balance": write_off_balance,
                    }
                )

        _logger.info(
            "Batch Payment - get_payment_values: partner=%s, amount=%s, "
            "write_off_count=%s, destination_account=%s",
            group_data.get("partner_id"),
            group_data.get("total"),
            len(res["write_off_line_vals"]),
            destination_account_id,
        )
        return res

    def _check_amounts(self):
        """Validate payment amounts before creating the payment records."""
        if not self.invoice_payments:
            return

        # If the invoice lines are still at their default residual values, the
        # user probably only edited the batch total. In that case, use the batch
        # total to distribute partial payments before creating the payment.
        if self._invoice_payments_are_default():
            self._fill_invoice_payments_from_batch_amount(
                self._get_batch_payment_amount(), persist=True
            )
            return

        if float_compare(
            self.total_amount,
            self.cheque_amount,
            precision_rounding=self.currency_id.rounding,
        ) != 0:
            raise ValidationError(
                _(
                    "The pay amount of the invoices and the batch payment total do not match."
                )
            )

    @api.onchange("cheque_amount")
    def _onchange_cheque_amount(self):
        """Keep the invoice lines in sync when the batch total is edited."""
        if self._invoice_payments_are_default():
            self._fill_invoice_payments_from_batch_amount(
                self.cheque_amount, persist=False
            )

    @api.onchange("amount")
    def _onchange_amount(self):
        """Mirror the standard amount field into the batch allocation."""
        if self._invoice_payments_are_default():
            self._fill_invoice_payments_from_batch_amount(
                self.amount, persist=False
            )

    def get_memo(self, memo, group_data, partner_id, data_get):
        if memo:
            memo = (
                group_data[partner_id]["memo"]
                + " : "
                + memo
                + "-"
                + str(data_get.invoice_id.name)
            )
        else:
            memo = (
                group_data[partner_id]["memo"] + " : " + str(data_get.invoice_id.name)
            )
        return memo

    def total_amount_in_words(self, data_get, old_total=0):
        check_amount_in_words = num2words(
            math.floor(old_total + data_get.amount)
        ).title()
        decimals = (old_total + data_get.amount) % 1
        if decimals >= 10**-2:
            check_amount_in_words += _(" and %s/100") % str(
                int(round(float_round(decimals * 100, precision_rounding=1)))
            )
        return check_amount_in_words

    def get_payment_invoice_value(self, name, data_get):
        return {
            "line_name": name,
            "amount": data_get.amount,
            "payment_difference_handling": data_get.payment_difference_handling,
            "payment_difference": data_get.payment_difference,
            "writeoff_account_id": data_get.writeoff_account_id
            and data_get.writeoff_account_id.id
            or False,
        }

    def update_group_pay_data(
        self, partner_id, group_data, data_get, check_amount_in_words
    ):
        # build memo value
        if self.communication:
            memo = self.communication + "-" + str(data_get.invoice_id.name)
        else:
            memo = str(data_get.invoice_id.name)
        name = ""
        if data_get.reason_code:
            name = str(data_get.reason_code.code)
        if data_get.note:
            name = name + ": " + str(data_get.note)
        if not name:
            name = "Counterpart"
        inv_val = {
            "line_name": name,
            "amount": data_get.amount,
            "payment_difference_handling": data_get.payment_difference_handling,
            "payment_difference": data_get.payment_difference,
            "writeoff_account_id": data_get.writeoff_account_id
            and data_get.writeoff_account_id.id
            or False,
        }
        group_data.update(
            {
                partner_id: {
                    "partner_id": partner_id,
                    "partner_type": MAP_INVOICE_TYPE_PARTNER_TYPE[
                        data_get.invoice_id.move_type
                    ],
                    "total": data_get.amount,
                    "check_amount_in_words": check_amount_in_words,
                    "memo": memo,
                    "temp_invoice": data_get.invoice_id.id,
                    "inv_val": {data_get.invoice_id.id: inv_val},
                }
            }
        )

    def get_amount(self, memo, group_data, line):
        line.payment_difference = line.balance - line.amount
        partner_id = line.invoice_id.partner_id.id
        if partner_id in group_data:
            old_total = group_data[partner_id]["total"]
            # build memo value
            if self.communication:
                memo = (
                    group_data[partner_id]["memo"]
                    + " : "
                    + self.communication
                    + "-"
                    + str(line.invoice_id.name)
                )
            else:
                memo = (
                    group_data[partner_id]["memo"] + " : " + str(line.invoice_id.name)
                )
            # Calculate amount in words
            check_amount_in_words = self.total_amount_in_words(line, old_total)
            group_data[partner_id].update(
                {
                    "partner_id": partner_id,
                    "partner_type": MAP_INVOICE_TYPE_PARTNER_TYPE[
                        line.invoice_id.move_type
                    ],
                    "total": old_total + line.amount,
                    "memo": memo,
                    "temp_invoice": line.invoice_id.id,
                    "check_amount_in_words": check_amount_in_words,
                }
            )
            # prepare name
            name = ""
            if line.reason_code:
                name = str(line.reason_code.code)
            if line.note:
                name = name + ": " + str(line.note)
            if not name:
                name = "Counterpart"
            # Update with payment diff data
            inv_val = self.get_payment_invoice_value(name, line)
            group_data[partner_id]["inv_val"].update({line.invoice_id.id: inv_val})
        else:
            # calculate amount in words
            check_amount_in_words = self.total_amount_in_words(line, 0)
            # prepare name
            self.update_group_pay_data(
                partner_id, group_data, line, check_amount_in_words
            )

    def action_create_payments(self):
        """Intercept native Odoo button click and route to our batch process
        if the user is using the batch payment UI (invoice_payments has lines)."""
        if self.invoice_payments:
            return self.make_payments()
        return super().action_create_payments()

    def make_payments(self):
        # Make group data either for Customers or Vendors
        context = dict(self._context or {})
        group_data = {}
        memo = self.communication or " "
        context.update({"is_customer": self.is_customer})

        # === CRITICAL DEBUG: write directly to file ===
        try:
            with open("/tmp/batch_payment_debug.log", "a") as f:
                f.write("=" * 60 + "\n")
                f.write(f"Batch Payment - make_payments CALLED. total_amount={self.total_amount}, cheque_amount={self.cheque_amount}\n")
                for pl in self.invoice_payments:
                    f.write(f"  LINE: invoice={pl.invoice_id.name}, balance={pl.balance}, amount={pl.amount}, diff={pl.payment_difference}, handling={pl.payment_difference_handling}\n")
        except Exception as e:
            pass

        self._check_amounts()
        for invoice_payment_line in self.invoice_payments:
            if invoice_payment_line.amount > 0:
                self.get_amount(memo, group_data, invoice_payment_line)

        _logger.info(
            "Batch Payment - make_payments: %d partners, group_data_keys=%s",
            len(group_data),
            list(group_data.keys()),
        )
        for pid, gd in group_data.items():
            _logger.info(
                "  Partner %s: total=%s, inv_val_keys=%s",
                pid, gd.get("total"),
                {k: v.get("amount") for k, v in gd.get("inv_val", {}).items()},
            )
            for inv_id, inv_data in gd.get("inv_val", {}).items():
                _logger.info(
                    "    Invoice %s: amount=%s, diff=%s, handling=%s",
                    inv_id,
                    inv_data.get("amount"),
                    inv_data.get("payment_difference"),
                    inv_data.get("payment_difference_handling"),
                )

        # update context
        context.update({"group_data": group_data})
        # making partner wise payment
        payment_ids = []
        for partner in list(group_data):
            # Build clean context: remove active_* keys to prevent Odoo
            # from overriding the partial amount with full invoice residual
            payment_context = context.copy()
            for key in list(payment_context.keys()):
                if key.startswith("active_"):
                    payment_context.pop(key)

            payment_vals = self.get_payment_values(
                group_data=group_data[partner]
            )
            _logger.info(
                "Batch Payment - creating payment: amount=%s, partner=%s",
                payment_vals.get("amount"),
                payment_vals.get("partner_id"),
            )

            # Use skip_invoice_sync to prevent Odoo from recalculating
            # the payment amount from linked invoice lines
            payment = (
                self.env["account.payment"]
                .with_context(**payment_context, skip_invoice_sync=True)
                .create(payment_vals)
            )
            _logger.info(
                "Batch Payment - payment created: id=%s, amount=%s, move=%s",
                payment.id,
                payment.amount,
                payment.move_id.id,
            )
            payment_ids.append(payment.id)
            payment.action_post()

            # Reconciliation
            def _get_line_filter(line):
                return (
                    line.account_id
                    and line.account_id.account_type
                    in ("asset_receivable", "liability_payable")
                    and not line.reconciled
                )

            payment_lines = payment.line_ids.filtered(_get_line_filter)
            partner_invoice_ids = list(
                group_data[partner].get("inv_val", {})
            )
            if not partner_invoice_ids:
                partner_invoice_ids = context.get("active_ids", [])
            invoices = self.env["account.move"].browse(partner_invoice_ids)
            lines = invoices.line_ids.filtered(_get_line_filter)

            _logger.info(
                "Batch Payment - reconciling: payment_lines=%s (amount=%s), "
                "invoice_lines=%s (residual=%s)",
                payment_lines.ids,
                sum(abs(l.amount_residual) for l in payment_lines),
                lines.ids,
                sum(abs(l.amount_residual) for l in lines),
            )

            # Manual precise reconciliation to respect exact partial amounts
            for invoice_line in lines:
                inv_id = invoice_line.move_id.id
                amount_to_pay = group_data[partner].get("inv_val", {}).get(inv_id, {}).get("amount", 0.0)

                if amount_to_pay > 0:
                    for pay_line in payment_lines:
                        if pay_line.account_id == invoice_line.account_id and not pay_line.reconciled and not invoice_line.reconciled:
                            amount = abs(amount_to_pay)
                            
                            if pay_line.balance > 0:
                                debit_move_id = pay_line.id
                                credit_move_id = invoice_line.id
                            else:
                                debit_move_id = invoice_line.id
                                credit_move_id = pay_line.id
                                
                            try:
                                self.env["account.partial.reconcile"].create({
                                    "debit_move_id": debit_move_id,
                                    "credit_move_id": credit_move_id,
                                    "amount": amount,
                                    "debit_amount_currency": amount,
                                    "credit_amount_currency": amount,
                                })
                            except Exception as e:
                                _logger.error("Failed to create partial reconcile for %s: %s", inv_id, e)
                                # Fallback to standard reconcile if manual fails
                                (pay_line + invoice_line).reconcile()
                            break

        if self._context.get("dont_redirect_to_payments"):
            return True

        action = {
            "name": _("Payments"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "context": {"create": False},
        }
        if len(payment_ids) == 1:
            action.update({
                "view_mode": "form",
                "res_id": payment_ids[0],
            })
        else:
            action.update({
                "view_mode": "tree,form",
                "domain": [("id", "in", payment_ids)],
            })
        return action

    def get_batch_payment_amount(self, invoice=None, payment_date=None):
        return {
            "amount": False,
            "payment_difference": False,
            "payment_difference_handling": False,
            "writeoff_account_id": False,
        }

    def get_invoice_payments_remaining_amount(self, remaining_amount, count):
        self._fill_invoice_payments_from_batch_amount(remaining_amount, persist=True)

    def auto_fill_payments(self):
        ctx = self._context.copy()
        batch_payment = self.cheque_amount
        remaining_amt = batch_payment
        count = 0
        for wizard in self:
            if wizard.invoice_payments:
                wizard.get_invoice_payments_remaining_amount(remaining_amt, count)
            ctx.update(
                {
                    "reference": wizard.communication or "",
                    "journal_id": wizard.journal_id.id,
                }
            )
        return {
            "name": _("Batch Payments"),
            "view_mode": "form",
            "view_id": False,
            "view_type": "form",
            "res_id": self.id,
            "res_model": "account.payment.register",
            "type": "ir.actions.act_window",
            "nodestroy": True,
            "target": "new",
            "context": ctx,
        }
