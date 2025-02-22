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
    ], default='pending', string='Approval Status')

    rejection_reason = fields.Text(string='Rejection Reason')
    rejection_date = fields.Datetime(string='Rejection Date')
    rejected_by = fields.Many2one('res.users', string='Rejected By')

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
            # เมื่อกดปุ่ม confirm เดิมจะเปลี่ยนสถานะเป็น waiting_l1 เพื่อเริ่มกระบวนการขออนุมัติระดับ L1
            order.write({'state': 'waiting_l1'})
            # ดึงผู้อนุมัติ L1 แล้วสร้างกิจกรรมแจ้งเตือน
            l1_users = self.env.ref('custom_purchase_approval.group_purchase_approval_l1').users
            for user in l1_users:
                order.sudo()._create_approval_activity(
                    user,
                    'L1 Approval Required',
                    f'Please review and approve Purchase Order: {order.name}'
                )
        return True

    def approve_l1(self):
        if not self.env.user.has_group('custom_purchase_approval.group_purchase_approval_l1'):
            raise UserError(_('You do not have permission to approve this PO.'))
        for order in self:
            if order.state == 'waiting_l1':
                # ลบกิจกรรมแจ้งเตือน L1 ที่เกี่ยวข้อง
                self.env['mail.activity'].search([
                    ('res_id', '=', order.id),
                    ('res_model', '=', 'purchase.order'),
                    ('user_id', 'in', self.env.ref('custom_purchase_approval.group_purchase_approval_l1').users.ids)
                ]).sudo().unlink()
                # เปลี่ยนสถานะเป็น waiting_l2 เพื่อรอการอนุมัติ L2
                order.write({'state': 'waiting_l2'})
                # ดึงผู้อนุมัติ L2 และสร้างกิจกรรมแจ้งเตือน
                l2_users = self.env.ref('custom_purchase_approval.group_purchase_approval_l2').users
                for user in l2_users:
                    order.sudo()._create_approval_activity(
                        user,
                        'L2 Approval Required',
                        f'Please review and approve Purchase Order: {order.name}'
                    )
        return True

    def approve_l2(self):
        if not self.env.user.has_group('custom_purchase_approval.group_purchase_approval_l2'):
            raise UserError(_('You do not have permission to approve this PO.'))
        for order in self:
            if order.state == 'waiting_l2':
                # ลบกิจกรรมแจ้งเตือน L2 ที่เกี่ยวข้อง
                self.env['mail.activity'].search([
                    ('res_id', '=', order.id),
                    ('res_model', '=', 'purchase.order'),
                    ('user_id', 'in', self.env.ref('custom_purchase_approval.group_purchase_approval_l2').users.ids)
                ]).sudo().unlink()

                # เปลี่ยนสถานะชั่วคราวกลับไปที่ draft เพื่อให้ workflow ยืนยัน PO ของ Odoo ทำงาน
                order.write({'state': 'draft'})

                # เรียกเมธอดพื้นฐาน button_confirm() จากโมดูล purchase เพื่อยืนยัน POและสร้าง picking
                super(PurchaseOrder, order).button_confirm()

                # หลังจากยืนยัน PO แล้ว อัพเดต field approval_state
                order.write({'approval_state': 'approved'})

                # ดำเนินการตรวจสอบและปรับปรุง receipt (stock picking) ที่เป็นประเภท incoming
                incoming_pickings = order.picking_ids.filtered(lambda p: p.picking_type_id.code == 'incoming')
                for picking in incoming_pickings:
                    if picking.state == 'draft':
                        picking.action_confirm()
                        picking.action_assign()
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
        # ลบกิจกรรมทั้งหมดที่เกี่ยวกับ PO
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
        # สร้างกิจกรรมแจ้งเตือนให้เจ้าของ PO ทราบการปฏิเสธ
        self.sudo()._create_approval_activity(
            self.create_uid,
            'PO Rejected',
            f'Purchase Order {self.name} has been rejected.\nReason: {reason}'
        )
        return True