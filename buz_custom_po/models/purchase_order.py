from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

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
            # เปลี่ยนสถานะเป็น waiting_l1 เพื่อรอการอนุมัติจาก L1
            order.write({
                'state': 'waiting_l1',
                'approval_state': 'pending'
            })
            
            # ส่งการแจ้งเตือนไปยังผู้อนุมัติ L1
            l1_users = self.env.ref('buz_custom_po.group_purchase_approval_l1').users
            for user in l1_users:
                order.sudo()._create_approval_activity(
                    user,
                    'L1 Approval Required',
                    f'Please review and approve Purchase Order: {order.name}'
                )
            
            # ส่งอีเมลแจ้งเตือนผู้อนุมัติ L1
            template = self.env.ref('buz_custom_po.email_template_po_approval_l1')
            if template:
                template.send_mail(order.id, force_send=True)
        return True

    def approve_l1(self):
        if not self.env.user.has_group('buz_custom_po.group_purchase_approval_l1'):
            raise UserError(_('You do not have permission to approve this PO.'))
            
        for order in self:
            if order.state == 'waiting_l1':
                # ลบกิจกรรมแจ้งเตือน L1
                self.env['mail.activity'].search([
                    ('res_id', '=', order.id),
                    ('res_model', '=', 'purchase.order'),
                    ('user_id', 'in', self.env.ref('buz_custom_po.group_purchase_approval_l1').users.ids)
                ]).sudo().unlink()

                # บันทึกข้อมูลการอนุมัติ L1
                order.write({
                    'state': 'waiting_l2',
                    'l1_approved_by': self.env.user.id,
                    'l1_approved_date': fields.Datetime.now()
                })

                # ส่งการแจ้งเตือนไปยังผู้อนุมัติ L2
                l2_users = self.env.ref('buz_custom_po.group_purchase_approval_l2').users
                for user in l2_users:
                    order.sudo()._create_approval_activity(
                        user,
                        'L2 Approval Required',
                        f'Please review and approve Purchase Order: {order.name}'
                    )

                # ส่งอีเมลแจ้งเตือนผู้อนุมัติ L2
                template = self.env.ref('buz_custom_po.email_template_po_approval_l2')
                if template:
                    template.send_mail(order.id, force_send=True)
        return True

    def approve_l2(self):
        if not self.env.user.has_group('buz_custom_po.group_purchase_approval_l2'):
            raise UserError(_('You do not have permission to approve this PO.'))
            
        for order in self:
            if order.state == 'waiting_l2':
                # ลบกิจกรรมแจ้งเตือน L2
                self.env['mail.activity'].search([
                    ('res_id', '=', order.id),
                    ('res_model', '=', 'purchase.order'),
                    ('user_id', 'in', self.env.ref('buz_custom_po.group_purchase_approval_l2').users.ids)
                ]).sudo().unlink()

                # บันทึกข้อมูลการอนุมัติ L2
                order.write({
                    'state': 'draft',  # เปลี่ยนกลับเป็น draft ชั่วคราวเพื่อให้ workflow มาตรฐานทำงาน
                    'l2_approved_by': self.env.user.id,
                    'l2_approved_date': fields.Datetime.now()
                })

                # เรียก method มาตรฐานเพื่อยืนยัน PO
                super(PurchaseOrder, order).button_confirm()
                
                # อัพเดทสถานะการอนุมัติ
                order.write({'approval_state': 'approved'})

                # ส่งอีเมลแจ้งผู้สร้าง PO ว่าได้รับการอนุมัติแล้ว
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
        # ลบกิจกรรมแจ้งเตือนทั้งหมด
        self.env['mail.activity'].search([
            ('res_id', '=', self.id),
            ('res_model', '=', 'purchase.order')
        ]).sudo().unlink()

        # บันทึกข้อมูลการปฏิเสธ
        self.write({
            'state': 'draft',
            'approval_state': 'rejected',
            'rejection_reason': reason,
            'rejection_date': fields.Datetime.now(),
            'rejected_by': self.env.user.id,
        })

        # สร้างกิจกรรมแจ้งเตือนผู้สร้าง PO
        self.sudo()._create_approval_activity(
            self.create_uid,
            'PO Rejected',
            f'Purchase Order {self.name} has been rejected.\nReason: {reason}'
        )

        # ส่งอีเมลแจ้งผู้สร้าง PO
        template = self.env.ref('buz_custom_po.email_template_po_rejected')
        if template:
            template.send_mail(self.id, force_send=True)
        return True