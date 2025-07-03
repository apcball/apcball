from odoo import models, fields, api, _
from odoo.exceptions import UserError
from num2words import num2words


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    requested_by_id = fields.Many2one('res.users', string='Requested By')
    buz_purchase_request_id = fields.Many2one('buz.purchase.request', string="Purchase Request")
    partner_contact_id = fields.Many2one('res.partner', string="Contact Person")
    name = fields.Char(string="Purchase Request Number")
    has_vat = fields.Boolean(string='Has VAT', compute='_compute_has_vat', store=False)

    state = fields.Selection(selection_add=[
        ('waiting_l1', 'Waiting L1 Approval'),
        ('waiting_l2', 'Waiting L2 Approval')
    ])

    approval_state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], default='pending', string='Approval Status', tracking=True)

    rejection_reason = fields.Text(string='Rejection Reason')
    rejection_date = fields.Datetime(string='Rejection Date')
    rejected_by = fields.Many2one('res.users', string='Rejected By')

    l1_approved_by = fields.Many2one('res.users', string='L1 Approved By', readonly=True)
    l1_approved_date = fields.Datetime(string='L1 Approved Date', readonly=True)
    l2_approved_by = fields.Many2one('res.users', string='L2 Approved By', readonly=True)
    l2_approved_date = fields.Datetime(string='L2 Approved Date', readonly=True)

    department_id = fields.Many2one('hr.department', string='Department')
    
    department_name = fields.Char(
        string='Department Name',
        compute='_compute_department_name',
        store=False
    )

    amount_total_text_th = fields.Char(
        string='Amount Total (Thai Text)',
        compute='_compute_amount_total_text_th',
        store=False
    )

    has_vat = fields.Boolean(
        string='Has VAT',
        compute='_compute_has_vat',
        store=False
    )

    @api.depends('order_line.taxes_id')
    def _compute_has_vat(self):
        for order in self:
            order.has_vat = any(
                tax.amount > 0 and 'vat' in (tax.tax_group_id.name or '').lower()
                for line in order.order_line
                for tax in line.taxes_id
            )


    @api.depends('order_line.taxes_id')
    def _compute_has_vat(self):
        for order in self:
            order.has_vat = any(
                line.taxes_id.filtered(lambda tax: tax.amount > 0.0 and tax.tax_group_id.name == 'VAT')
                for line in order.order_line
            )
            
    @api.depends('order_line.taxes_id')
    def _compute_has_vat(self):
        for order in self:
            order.has_vat = any(
                line.taxes_id.filtered(lambda tax: tax.amount > 0.0 and 'vat' in (tax.tax_group_id.name or '').lower())
                for line in order.order_line
            )        

    @api.depends('amount_total')
    def _compute_amount_total_text_th(self):
        for rec in self:
            if rec.currency_id and rec.amount_total is not None:
               rec.amount_total_text_th = rec._baht_text_th(rec.amount_total)
            else:
                rec.amount_total_text_th = "-"                 

    def _baht_text_th(self, amount):
        t1 = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
        t2 = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]

        def num2thai(number):
            number = int(number)
            if number == 0:
                return t1[0]

            result = ""
            digits = list(str(number))
            length = len(digits)

            for i in range(length):
                n = int(digits[i])
                pos = length - i - 1

                if n == 0:
                    continue

                # ตำแหน่งหลักสิบ
                if pos == 1:
                    if n == 1:
                        result += t2[1]
                    elif n == 2:
                        result += "ยี่" + t2[1]
                    else:
                        result += t1[n] + t2[1]
                # ตำแหน่งหลักหน่วย
                elif pos == 0:
                    result += t1[n]
                # ตำแหน่งอื่น ๆ
                else:
                    result += t1[n] + t2[pos]

            return result

        amount = round(amount, 2)
        baht = int(amount)
        satang = int(round((amount - baht) * 100))

        result = num2thai(baht) + "บาท"
        if satang > 0:
            result += num2thai(satang) + "สตางค์"
        else:
            result += "ถ้วน"
        return result

    def _compute_department_name(self):
        for rec in self:
            rec.department_name = rec.department_id.name if rec.department_id else '-'

    def _create_approval_activity(self, user, summary, note):
        self.env['mail.activity'].sudo().create({
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
            'note': note,
            'summary': summary,
            'user_id': user.id,
            'res_id': self.id,
            'res_model_id': self.env['ir.model']._get('purchase.order').id
        })

    def button_confirm(self):
        for order in self:
            order.write({
                'state': 'waiting_l1',
                'approval_state': 'pending'
            })
            l1_users = self.env.ref('buz_custom_po.group_purchase_approval_l1').users
            for user in l1_users:
                order.sudo()._create_approval_activity(
                    user,
                    'L1 Approval Required',
                    f'Please review and approve Purchase Order: {order.name}'
                )
            template = self.env.ref('buz_custom_po.email_template_po_approval_l1')
            if template:
                template.send_mail(order.id, force_send=True)
        return True

    def approve_l1(self):
        if not self.env.user.has_group('buz_custom_po.group_purchase_approval_l1'):
            raise UserError(_('You do not have permission to approve this PO.'))

        for order in self:
            if order.state == 'waiting_l1':
                self.env['mail.activity'].search([
                    ('res_id', '=', order.id),
                    ('res_model', '=', 'purchase.order'),
                    ('user_id', 'in', self.env.ref('buz_custom_po.group_purchase_approval_l1').users.ids)
                ]).sudo().unlink()

                order.write({
                    'state': 'waiting_l2',
                    'l1_approved_by': self.env.user.id,
                    'l1_approved_date': fields.Datetime.now()
                })

                l2_users = self.env.ref('buz_custom_po.group_purchase_approval_l2').users
                for user in l2_users:
                    order.sudo()._create_approval_activity(
                        user,
                        'L2 Approval Required',
                        f'Please review and approve Purchase Order: {order.name}'
                    )

                template = self.env.ref('buz_custom_po.email_template_po_approval_l2')
                if template:
                    template.send_mail(order.id, force_send=True)
        return True

    def approve_l2(self):
        if not self.env.user.has_group('buz_custom_po.group_purchase_approval_l2'):
            raise UserError(_('You do not have permission to approve this PO.'))

        for order in self:
            if order.state == 'waiting_l2':
                self.env['mail.activity'].search([
                    ('res_id', '=', order.id),
                    ('res_model', '=', 'purchase.order'),
                    ('user_id', 'in', self.env.ref('buz_custom_po.group_purchase_approval_l2').users.ids)
                ]).sudo().unlink()

                order.write({
                    'state': 'draft',
                    'l2_approved_by': self.env.user.id,
                    'l2_approved_date': fields.Datetime.now()
                })

                super(PurchaseOrder, order).button_confirm()
                order.write({'approval_state': 'approved'})

                template = self.env.ref('buz_custom_po.email_template_po_approved')
                if template:
                    template.send_mail(order.id, force_send=True)
        return True

    def action_reject(self):
        return {
            'name': _('Reject Purchase Order'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'purchase.order.reject.wizard',
            'target': 'new',
            'context': {'default_purchase_order_id': self.id}
        }

    def reject_approval(self, reason):
        self.env['mail.activity'].search([
            ('res_id', '=', self.id),
            ('res_model', '=', 'purchase.order')
        ]).sudo().unlink()

        self.write({
            'state': 'draft',
            'approval_state': 'rejected',
            'rejection_reason': reason,
            'rejection_date': fields.Datetime.now(),
            'rejected_by': self.env.user.id,
        })

        self.sudo()._create_approval_activity(
            self.create_uid,
            'PO Rejected',
            f'Purchase Order {self.name} has been rejected.\nReason: {reason}'
        )

        template = self.env.ref('buz_custom_po.email_template_po_rejected')
        if template:
            template.send_mail(self.id, force_send=True)
        return True
