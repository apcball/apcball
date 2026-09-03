# -*- coding: utf-8 -*-

from odoo import models, api, fields, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_last_sequence_domain(self, relaxed=False):
        """ใช้เลข Payment เดิมของ Journal ได้แม้ข้อมูลเก่าขาด payment_id.

        Payment บางรายการในฐานข้อมูลเดิมมี account_payment.move_id ครบ แต่
        account_move.payment_id ไม่ถูกเติมไว้ ทำให้ sequence ของ Odoo 17
        กรองรายการเหล่านั้นออกและอาจเริ่มเลข Payment ซ้ำจากเลขแรกของปี
        การปรับนี้ใช้เฉพาะบริบท Customer Refund CV และกรองด้วย prefix ของ
        Payment Journal โดยตรง จึงไม่เปลี่ยนพฤติกรรมของรายการบัญชีทั่วไป
        หรือ Payment flow อื่น
        """
        where_string, param = super()._get_last_sequence_domain(relaxed=relaxed)
        if (
            not relaxed
            and self.env.context.get('buz_customer_refund_voucher_id')
            and self.journal_id
            and self.journal_id.payment_sequence
        ):
            # ให้ legacy payment moves ที่ payment_id ว่างยังมีส่วนร่วมในการ
            # หาเลขล่าสุด แต่ไม่ดึงเลขของรายการบัญชีปกติ (เช่น BNK1/...)
            where_string = where_string.replace(
                ' AND payment_id IS NOT NULL ', ' '
            ).replace(
                ' AND payment_id IS NULL ', ' '
            )
            param['cv_payment_sequence_prefix'] = (
                f"P{self.journal_id.code}/%"
            )
            where_string += (
                ' AND sequence_prefix LIKE %(cv_payment_sequence_prefix)s'
            )
        return where_string, param

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

    # Customer Refund PV helpers
    def _get_cv_active(self):
        self.ensure_one()
        CV = self.env['buz.customer.refund.voucher']
        # active states: draft/confirmed/in_payment/exception
        candidates = CV.search([('credit_note_id', '=', self.id)])
        for cv in candidates:
            if cv.workflow_state in ('draft', 'confirmed', 'in_payment', 'exception'):
                return cv
        return CV.browse()

    def action_create_customer_refund_voucher(self):
        self.ensure_one()
        if self.move_type != 'out_refund' or self.state != 'posted':
            raise UserError(_("Only Posted Customer Credit Note can create Refund PV."))
        residual = abs(self.amount_residual_signed) if hasattr(self, 'amount_residual_signed') else abs(self.amount_residual)
        if residual < 0.01:
            raise UserError(_("Credit Note has no residual."))
        CV = self.env['buz.customer.refund.voucher']
        active = self._get_cv_active()
        if active:
            # open existing instead of creating
            return {
                'name': _('Customer Refund PV'),
                'type': 'ir.actions.act_window',
                'res_model': 'buz.customer.refund.voucher',
                'view_mode': 'form',
                'res_id': active.id,
                'target': 'current',
            }
        # check if there is any non-active that still blocks? Only active blocks, so we can create next if previous is paid/partially etc and residual remains
        # create new CV
        cv = CV.create({
            'credit_note_id': self.id,
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'date': fields.Date.context_today(self),
            'planned_payment_date': fields.Date.context_today(self),
        })
        return {
            'name': _('Customer Refund PV'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.customer.refund.voucher',
            'view_mode': 'form',
            'res_id': cv.id,
            'target': 'current',
        }

    def action_open_customer_refund_vouchers(self):
        self.ensure_one()
        return {
            'name': _('Customer Refund PVs'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.customer.refund.voucher',
            'view_mode': 'tree,form',
            'domain': [('credit_note_id', '=', self.id)],
            'context': {'create': False},
        }

    customer_refund_voucher_count = fields.Integer(compute="_compute_cv_count", string="Refund PV Count")
    customer_refund_voucher_ids = fields.One2many('buz.customer.refund.voucher', 'credit_note_id', string="Refund PVs")

    @api.depends('customer_refund_voucher_ids')
    def _compute_cv_count(self):
        for rec in self:
            rec.customer_refund_voucher_count = len(rec.customer_refund_voucher_ids)
