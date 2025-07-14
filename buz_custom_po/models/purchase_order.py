from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    requested_by_id = fields.Many2one('res.users', string='Requested By')
    buz_purchase_request_id = fields.Many2one('buz.purchase.request', string="Purchase Request")
    partner_contact_id = fields.Many2one('res.partner', string="Contact Person")
    client_order_ref = fields.Char(string='Customer Reference')
    employee_contact_id = fields.Many2one('res.partner', string="Contact Person")
    payment_term_id = fields.Many2one('account.payment.term', string="Payment Term")
    date_order = fields.Datetime(string="Order Date")
    date_planned = fields.Date(string='Planned Date', default=fields.Date.context_today)
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True)
    purchase_ids = fields.One2many('purchase.order', 'requisition_id', string="Purchase Orders")
    department_id = fields.Many2one('hr.department', string='Department')
    requisition_id = fields.Many2one('purchase.requisition', string='Purchase Agreement')
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True)
    custom_request_date = fields.Date(string="วันที่ตามแบบฟอร์ม")
    delivery_date = fields.Date(string="วันที่ส่งมอบ")
    project_id = fields.Many2one('project.project', string="Project")
    remarks = fields.Char(string="หมายเหตุ")
    district_id = fields.Many2one('res.country.district', string="ตำบล")

    department_name = fields.Char(
        string='Department Name',
        compute='_compute_department_name',
        store=False
    )
    

    department_id = fields.Many2one(
        'hr.department',
        string="แผนก",
        related='user_id.employee_id.department_id',
        store=True,
        readonly=True
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

    # Temporary field to allow clean migration - will be removed in next version
    approval_state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),  
        ('rejected', 'Rejected')
    ], string='Approval Status')

    @api.depends('order_line.taxes_id')
    def _compute_has_vat(self):
        for order in self:
            order.has_vat = any(
                line.taxes_id.filtered(lambda tax: tax.amount > 0.0 and 'vat' in (tax.tax_group_id.name or '').lower())
                for line in order.order_line
            )        

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['purchase.order'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'purchase.order',
            'docs': docs,
        }
    
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

    def button_confirm(self):
        return super(PurchaseOrder, self).button_confirm()

    def name_get(self):
        result = []
        for rec in self:
            name = rec.description or "รายการ"
        result.append((rec.id, name))
        return result    


class BuzPurchaseOrderLine(models.Model):
    _name = 'buz.purchase.order.line'
    _description = 'Custom Purchase Order Line'

    order_id = fields.Many2one('purchase.order', string='Purchase Order', ondelete='cascade')
    quantity = fields.Float(string='จำนวน')
    unit_id = fields.Many2one('uom.uom', string='หน่วย')
    description = fields.Text(string='ชื่อและรายละเอียดสิ่งที่ต้องการ')
    unit_price = fields.Float(string='ราคาต่อหน่วย')
    remark = fields.Char(string='หมายเหตุ')