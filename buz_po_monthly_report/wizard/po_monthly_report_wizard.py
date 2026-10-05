import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PurchaseOrderMonthlyReportWizard(models.TransientModel):
    _name = 'po.monthly.report.wizard'
    _description = 'Purchase Order Monthly Report Wizard'

    po_date_from = fields.Date(string='วันที่เปิด PO ตั้งแต่')
    po_date_to = fields.Date(string='วันที่เปิด PO ถึง')
    file_data = fields.Binary(string='Excel File', readonly=True, attachment=False)
    file_name = fields.Char(string='File Name', readonly=True)

    @api.constrains('po_date_from', 'po_date_to')
    def _check_date_ranges(self):
        for wizard in self:
            has_po_range = bool(wizard.po_date_from or wizard.po_date_to)
            if not has_po_range:
                raise ValidationError(_(
                    'กรุณาระบุช่วงวันที่เปิด PO'
                ))
            if has_po_range and not (wizard.po_date_from and wizard.po_date_to):
                raise ValidationError(_(
                    'กรุณาระบุวันที่เริ่มต้นและสิ้นสุดของช่วงวันที่เปิด PO ให้ครบถ้วน'
                ))
            if wizard.po_date_from and wizard.po_date_from > wizard.po_date_to:
                raise ValidationError(_(
                    'วันที่เริ่มต้น PO ต้องไม่อยู่หลังวันที่สิ้นสุด'
                ))

    def action_export_xlsx(self):
        self.ensure_one()
        self._check_date_ranges()
        content = self.env[
            'buz.po.monthly.report.xlsx.generator'
        ].generate_xlsx(self)
        if not content:
            raise UserError(_('ไม่สามารถสร้างไฟล์ Excel ได้'))
        self.write({
            'file_data': base64.b64encode(content),
            'file_name': 'Purchase_Order_Monthly_Report.xlsx',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': (
                '/web/content/?model=po.monthly.report.wizard&id=%s'
                '&field=file_data&filename_field=file_name&download=true'
            ) % self.id,
            'target': 'self',
        }
