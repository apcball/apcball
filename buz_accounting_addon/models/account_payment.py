from odoo import fields, models, _
from odoo.exceptions import UserError


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

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        """Add Other Income to the Refund PV payment move only.

        ยอด Payment ยังคงเป็น Refund Amount เพื่อให้ Bank/Cash ถูกเครดิตตามเงินจริง
        และใช้ write-off line เพิ่ม Dr ลูกหนี้/Cr รายได้อื่นใน Journal Entry เดียวกัน
        ทำให้ Credit Note ถูก reconcile ได้เต็ม residual
        """
        self.ensure_one()
        write_off_line_vals = list(write_off_line_vals or [])
        pv = self.buz_customer_refund_pv_id
        if pv and pv.other_income_dis > 0:
            income_account = pv.other_income_account_id
            if not income_account:
                raise UserError(_("Please select an Other Income Account before registering payment."))
            income_amount = self.company_id.currency_id._convert(
                pv.other_income_dis, self.currency_id, self.company_id, self.date,
            )
            write_off_line_vals.append({
                'name': _('Other Income - %s') % pv.name,
                'account_id': income_account.id,
                'partner_id': pv.partner_id.id,
                'date_maturity': self.date,
                'amount_currency': -income_amount,
                'currency_id': self.currency_id.id,
                'balance': -pv.other_income_dis,
            })
        return super()._prepare_move_line_default_vals(
            write_off_line_vals, force_balance=force_balance,
        )
