from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    buz_payment_voucher_id = fields.Many2one(
        'account.payment.voucher',
        string='Payment Voucher',
        ondelete='set null',
        index=True,
        copy=False,
    )
    buz_customer_refund_pv_id = fields.Many2one(
        'buz.customer.refund.pv',
        string='Customer Refund PV',
        ondelete='set null',
        index=True,
        copy=False,
    )

    def write(self, vals):
        # ล็อกเลข Payment สำหรับ Refund PV: แก้ได้เฉพาะ Draft, ห้ามหลัง Post, ตรวจเลขซ้ำใน Journal+Company
        if 'name' in vals and vals.get('name'):
            for pay in self:
                if pay.buz_customer_refund_pv_id:
                    if pay.state != 'draft':
                        raise UserError(_("Cannot edit Payment number after posting. Payment %s is already %s. Use Reset to Draft or Reverse.") % (pay.name or '', pay.state))
                    new_name = vals['name']
                    if new_name and new_name != '/' and new_name != pay.name:
                        # ตรวจเลขซ้ำภายใน Journal และ Company เดียวกัน (เหมือน spec)
                        duplicate = self.env['account.move'].search_count([
                            ('name', '=', new_name),
                            ('journal_id', '=', pay.journal_id.id),
                            ('company_id', '=', pay.company_id.id),
                            ('id', '!=', pay.move_id.id),
                            ('state', '!=', 'cancel'),
                        ])
                        if duplicate:
                            raise UserError(_("Payment number '%s' already exists in journal '%s' for company '%s'.") % (new_name, pay.journal_id.display_name, pay.company_id.display_name))
                        # Also check payment name duplicate via move
                        dup_pay = self.env['account.payment'].search_count([
                            ('name', '=', new_name),
                            ('journal_id', '=', pay.journal_id.id),
                            ('company_id', '=', pay.company_id.id),
                            ('id', '!=', pay.id),
                        ])
                        if dup_pay:
                            raise UserError(_("Payment number '%s' already exists in journal '%s'.") % (new_name, pay.journal_id.display_name))
        return super().write(vals)

    def action_post(self):
        res = super().action_post()
        # หลัง Post ให้ Reconcile กับ Credit Note ตาม Refund PV (เฉพาะ Draft->Posted ที่สร้างจาก Refund PV)
        for pay in self:
            if not pay.buz_customer_refund_pv_id:
                continue
            # Only for payments that are now posted and have a PV
            if pay.state != 'posted':
                continue
            pv = pay.buz_customer_refund_pv_id
            credit_note = pv.credit_note_id
            if not credit_note or credit_note.state != 'posted':
                continue
            # Reconcile only if not already reconciled and amount matches refund_amount
            try:
                # หา lines ที่ยังไม่ reconciled และเป็น receivable
                payment_receivable_lines = pay.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable') and not l.reconciled
                )
                credit_receivable_lines = credit_note.line_ids.filtered(
                    lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable') and not l.reconciled
                )
                # Use same domain as core _reconcile_payments: parent_state posted, account_type valid, reconciled false
                # Try to reconcile per account
                for account in (payment_receivable_lines.account_id | credit_receivable_lines.account_id):
                    p_lines = payment_receivable_lines.filtered(lambda l: l.account_id == account and not l.reconciled)
                    c_lines = credit_receivable_lines.filtered(lambda l: l.account_id == account and not l.reconciled)
                    if p_lines and c_lines:
                        (p_lines + c_lines).reconcile()
                        _logger.info("Reconciled Draft Refund PV payment %s (%s) with Credit Note %s after Post", pay.name, pay.id, credit_note.name)
            except Exception as e:
                _logger.warning("Failed to auto-reconcile Refund PV payment %s with Credit Note %s after Post: %s", pay.name, credit_note.name if credit_note else 'N/A', str(e))
        return res

