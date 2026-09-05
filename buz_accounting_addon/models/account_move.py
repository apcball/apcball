# -*- coding: utf-8 -*-

from odoo import models, api, fields, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    customer_refund_pv_count = fields.Integer(
        string="Refund PV Count",
        compute="_compute_customer_refund_pv_count",
    )
    customer_refund_pv_ids = fields.One2many(
        "buz.customer.refund.pv",
        "credit_note_id",
        string="Refund PVs",
        readonly=True,
    )

    @api.depends("customer_refund_pv_ids")
    def _compute_customer_refund_pv_count(self):
        for move in self:
            # Use search to avoid cache issues on newly created PVs
            move.customer_refund_pv_count = self.env["buz.customer.refund.pv"].search_count([
                ("credit_note_id", "=", move.id)
            ])

    def action_create_customer_refund_pv(self):
        """Phase 1: Create Draft Customer Refund PV from Posted out_refund and open its form."""
        self.ensure_one()
        if self.move_type != "out_refund":
            raise UserError(_("Only Customer Credit Note (out_refund) can create a Refund PV."))
        if self.state != "posted":
            raise UserError(_("Credit Note must be Posted to create a Refund PV."))
        # Phase 1: do NOT create account.payment, do NOT reconcile, do NOT change credit note amounts/state
        vals = {
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "credit_note_id": self.id,
            "date": fields.Date.context_today(self),
        }
        pv = self.env["buz.customer.refund.pv"].create(vals)
        # Prefill one line from the credit note (optional but keeps totals visible)
        try:
            residual = abs(self.amount_residual_signed) if hasattr(self, "amount_residual_signed") else abs(self.amount_residual)
        except Exception:
            residual = abs(self.amount_total)
        if residual:
            untaxed = 0.0
            try:
                untaxed = abs(self.amount_untaxed_signed) if hasattr(self, "amount_untaxed_signed") else abs(self.amount_untaxed)
            except Exception:
                untaxed = residual
            pv.write({
                "line_ids": [fields.Command.create({
                    "move_id": self.id,
                    "amount_to_pay_gross": residual,
                    "wht_base_amount": untaxed,
                })]
            })
        # Phase 1: credit_note_id must be readonly in the form (enforced in view attrs)
        return {
            "name": _("Customer Refund PV"),
            "type": "ir.actions.act_window",
            "res_model": "buz.customer.refund.pv",
            "view_mode": "form",
            "res_id": pv.id,
            "target": "current",
        }

    def action_view_customer_refund_pvs(self):
        self.ensure_one()
        pvs = self.env["buz.customer.refund.pv"].search([("credit_note_id", "=", self.id)])
        action = {
            "name": _("Customer Refund PVs"),
            "type": "ir.actions.act_window",
            "res_model": "buz.customer.refund.pv",
            "view_mode": "tree,form",
            "domain": [("id", "in", pvs.ids)],
            "context": {"default_credit_note_id": self.id, "default_partner_id": self.partner_id.id, "default_company_id": self.company_id.id},
        }
        if len(pvs) == 1:
            action.update({"view_mode": "form", "res_id": pvs.id})
        return action

    def _auto_init(self):
        # Drop the conflicting constraint from employee_advance if it exists
        # This fixes the Validation Error: account_move_wht_tax_id_fkey
        # The constraint blocks deletions because it points to account_tax
        # and was created by a previous version of employee_advance using the same field name as l10n_th_account_tax.
        try:
            self.env.cr.execute("""
                ALTER TABLE account_move DROP CONSTRAINT IF EXISTS account_move_wht_tax_id_fkey;
            """)
        except Exception:
            pass
        return super()._auto_init()

    @api.depends('line_ids.amount_residual')
    def _compute_amount(self):
        """
        Override to consider invoices reconciled with Outstanding Receipts as fully paid.
        
        Standard Odoo considers Outstanding Receipts as "in_payment" status,
        but for our AR process, once reconciled with Outstanding Receipts,
        the invoice should be considered "paid" even before bank reconciliation.
        
        This behavior can be controlled via:
        Settings > Accounting > Configuration > Consider Outstanding Receipts as Paid
        """
        # Call parent method first
        super(AccountMove, self)._compute_amount()
        
        # Check if the feature is enabled
        ar_outstanding_as_paid = self.env['ir.config_parameter'].sudo().get_param(
            'buz_accounting_addon.ar_outstanding_as_paid', 'True'
        ) == 'True'
        
        # If feature is disabled, use standard Odoo behavior
        if not ar_outstanding_as_paid:
            return
        
        # For customer invoices, check if reconciled with Outstanding Receipts
        for move in self:
            # Only process customer invoices/refunds that show "in_payment"
            if move.move_type not in ('out_invoice', 'out_refund'):
                continue
            
            if move.payment_state != 'in_payment':
                continue
            
            # Check if the receivable line is fully reconciled
            if move.amount_residual != 0:
                continue
            
            # Find the receivable line
            receivable_line = move.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable'
            )
            
            if not receivable_line:
                continue
            
            # If fully reconciled (amount_residual = 0), consider it paid
            # regardless of whether it's reconciled with Outstanding Receipts or Bank
            if receivable_line.reconciled and move.amount_residual == 0:
                # Check if any of the reconciled lines come from Outstanding Receipts account
                has_outstanding_reconcile = False
                
                # Check matched credits (for invoices - debit on receivable)
                for partial in receivable_line.matched_credit_ids:
                    credit_line = partial.credit_move_id
                    if credit_line and credit_line.account_id.account_type not in (
                        'asset_receivable', 'liability_payable'
                    ):
                        # This is reconciled with a payment account (Outstanding or Bank)
                        has_outstanding_reconcile = True
                        break
                
                # Check matched debits (for refunds - credit on receivable)
                if not has_outstanding_reconcile:
                    for partial in receivable_line.matched_debit_ids:
                        debit_line = partial.debit_move_id
                        if debit_line and debit_line.account_id.account_type not in (
                            'asset_receivable', 'liability_payable'
                        ):
                            # This is reconciled with a payment account
                            has_outstanding_reconcile = True
                            break
                
                # If reconciled with payment account (Outstanding or Bank) and residual = 0,
                # consider it paid
                if has_outstanding_reconcile:
                    move.payment_state = 'paid'
