from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    requested_by_id = fields.Many2one('res.users', string='Requested By')
    buz_purchase_request_id = fields.Many2one('buz.purchase.request', string="Purchase Request")
    partner_contact_id = fields.Many2one('res.partner', string="Contact Person")
    criteria = fields.Char(string="Criteria")
    client_order_ref = fields.Char(string='Customer Reference')
    employee_contact_id = fields.Many2one('res.partner', string="Contact Person")
    payment_term_id = fields.Many2one('account.payment.term', string="Payment Term")
    date_order = fields.Datetime(string="Order Date")
    date_planned = fields.Date(string='Planned Date', default=fields.Date.context_today)
    vendor_id = fields.Many2one('res.partner', string='Vendor')  # กรณียังไม่มี vendor_id
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True)
    purchase_ids = fields.One2many('purchase.order', 'requisition_id', string="Purchase Orders")
    department_id = fields.Many2one('hr.department', string='Department')
    requisition_id = fields.Many2one('purchase.requisition', string='Purchase Agreement')

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
