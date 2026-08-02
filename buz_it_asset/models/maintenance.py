from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ITAssetMaintenance(models.Model):
    _name = 'buz.it.asset.maintenance'
    _description = 'IT Asset Maintenance History'
    _check_company_auto = True
    _order = 'sent_date desc, id desc'

    asset_id = fields.Many2one(
        'buz.it.asset', required=True, ondelete='restrict', check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company', related='asset_id.company_id', store=True, readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True,
        readonly=True,
    )
    sent_date = fields.Date(
        string='วันที่ส่งซ่อม (Sent Date)', required=True,
        default=fields.Date.context_today,
    )
    symptom = fields.Text(string='อาการเสีย (Problem Description)', required=True)
    state = fields.Selection([
        ('sent', 'ส่งซ่อม (Sent)'),
        ('in_progress', 'กำลังซ่อม (In Progress)'),
        ('done', 'ซ่อมเสร็จ (Completed)'),
        ('cancelled', 'ยกเลิก (Cancelled)'),
    ], string='สถานะ (Status)', required=True, default='sent')
    completed_date = fields.Date(string='วันที่ซ่อมเสร็จ (Completed Date)')
    technician_employee_id = fields.Many2one(
        'hr.employee', string='ช่างภายใน (Internal Technician)',
        ondelete='restrict', check_company=True,
    )
    external_technician_name = fields.Char(
        string='ชื่อช่างภายนอก (External Technician)',
    )
    vendor_id = fields.Many2one(
        'res.partner', string='ร้านซ่อม/ผู้ขาย (Repair Vendor)',
        ondelete='restrict', check_company=True,
    )
    cost = fields.Monetary(
        string='ค่าใช้จ่าย (Cost)', currency_field='currency_id',
    )
    attachment_ids = fields.Many2many(
        'ir.attachment', 'buz_it_asset_maintenance_attachment_rel',
        'maintenance_id', 'attachment_id', string='เอกสารแนบ (Attachments)',
        copy=False,
    )
    notes = fields.Text(string='หมายเหตุ (Notes)')

    @api.onchange('state')
    def _onchange_state(self):
        for record in self:
            if record.state == 'done' and not record.completed_date:
                record.completed_date = fields.Date.context_today(record)
            elif record.state != 'done':
                record.completed_date = False

    @api.constrains(
        'asset_id', 'company_id', 'technician_employee_id', 'vendor_id',
        'external_technician_name', 'state', 'completed_date', 'sent_date',
    )
    def _check_maintenance_details(self):
        for record in self:
            if record.technician_employee_id and record.external_technician_name:
                raise ValidationError(_(
                    'Select an internal technician or enter an external technician, not both.'
                ))
            for linked in (record.technician_employee_id, record.vendor_id):
                if linked and linked.company_id and linked.company_id != record.company_id:
                    raise ValidationError(_(
                        'The technician and repair vendor must belong to the asset company.'
                    ))
            if record.state == 'done' and not record.completed_date:
                raise ValidationError(_('Enter the completed date for completed maintenance.'))
            if (record.sent_date and record.completed_date
                    and record.completed_date < record.sent_date):
                raise ValidationError(_(
                    'The completed date cannot be earlier than the sent date.'
                ))

    def action_start(self):
        self.write({'state': 'in_progress', 'completed_date': False})
        return True

    def action_done(self):
        self.write({
            'state': 'done',
            'completed_date': fields.Date.context_today(self),
        })
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled', 'completed_date': False})
        return True

    def unlink(self):
        if any(record.state == 'done' for record in self):
            raise UserError(_('Completed maintenance history cannot be deleted.'))
        return super().unlink()
