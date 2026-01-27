from odoo import models, api

class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    def _notify_record_by_email(self, message, partner_ids, force_send=False, send_after_commit=True):
        # Override method นี้เพื่อไม่ให้มีการส่ง email ใด ๆ สำหรับ expense
        return {}

    @api.model
    def message_post(self, **kwargs):
        # ป้องกันไม่ให้ส่ง email notification
        kwargs.setdefault('mail_notify', False)
        kwargs.pop('email_from', None)
        return super(HrExpenseSheet, self).message_post(**kwargs)