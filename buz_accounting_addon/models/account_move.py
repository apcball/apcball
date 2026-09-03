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

    def action_register_payment(self):
        # Phase next: For Customer Credit Note with confirmed Refund PV, use refund_amount as initial payment amount
        # Do not create new button, reuse existing Register Payment button on Credit Note
        if self:
            # Only handle single out_refund with linked Refund PV, otherwise fall back to standard
            moves = self.filtered(lambda m: m.move_type == 'out_refund' and m.customer_refund_pv_ids)
            if len(moves) == 1 and len(self) == 1:
                move = moves[0]
                # Find the latest posted Refund PV with refund_amount
                refund_pv = move.customer_refund_pv_ids.filtered(lambda r: r.state == 'posted' and r.refund_amount and r.refund_amount > 0).sorted(key=lambda r: r.id, reverse=True)[:1]
                if refund_pv:
                    # Validations per spec: must be confirmed, have refund_amount, not already registered, not exceed residual
                    if refund_pv.payment_ids.filtered(lambda p: p.state != 'cancel'):
                        raise UserError(_("Payment already registered for Refund PV %s.") % refund_pv.name)
                    try:
                        residual = abs(move.amount_residual_signed) if hasattr(move, 'amount_residual_signed') else abs(move.amount_residual)
                    except Exception:
                        residual = abs(move.amount_total)
                    if refund_pv.refund_amount - residual > 1e-6:
                        raise UserError(_("Refund Amount (%.2f) exceeds remaining balance of Credit Note %s (%.2f).") % (refund_pv.refund_amount, move.name, residual))
                    # Prepare context to force amount and link to PV
                    ctx = dict(self.env.context)
                    ctx.update({
                        'buz_customer_refund_pv_id': refund_pv.id,
                        'force_amount': refund_pv.refund_amount,
                    })
                    if refund_pv.destination_journal_id:
                        ctx['default_journal_id'] = refund_pv.destination_journal_id.id
                    if refund_pv.date:
                        ctx['default_payment_date'] = refund_pv.date
                    # Use standard mechanism with forced context
                    return super(AccountMove, self.with_context(ctx)).action_register_payment()
                elif move.customer_refund_pv_ids.filtered(lambda r: r.state == 'draft'):
                    raise UserError(_("Refund PV must be confirmed before Register Payment."))
        return super().action_register_payment()

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
