from odoo import api, fields, models
from datetime import timedelta

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    purchase_price = fields.Float(string='Purchase Price', digits='Product Price')

    discount_percent = fields.Float(string='Discount Percent', compute='_compute_discount_percent', store=True)
    net_price = fields.Float(string='Net Price', compute='_compute_net_price', store=True)

    @api.depends('price_unit', 'normal_price')
    def _compute_discount_percent(self):
        for line in self:
            if hasattr(line, 'normal_price') and line.normal_price and line.normal_price > 0:
                line.discount_percent = round((1 - (line.price_unit / line.normal_price)) * 100, 2)
            else:
                line.discount_percent = line.discount

    @api.depends('normal_price', 'discount_percent')
    def _compute_net_price(self):
        for line in self:
            if hasattr(line, 'normal_price') and line.normal_price:
                line.net_price = line.normal_price - (line.normal_price * line.discount_percent / 100)
            else:
                line.net_price = 0.0

    @api.onchange('product_id')
    def _onchange_product_id_set_purchase_price(self):
        if self.product_id:
            self.purchase_price = self.product_id.standard_price

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    proposal_no = fields.Char(string='Proposal Number', readonly=True, copy=False)
    quotation_no = fields.Char(string='Quotation Number', copy=False)
    project_name = fields.Char(string='Project Name')
    customer_name = fields.Char(string='Customer Name')
    terms_conditions = fields.Text(string='Terms and Conditions')

    def _get_terms_conditions(self):
        expiry_date = (fields.Date.today() + timedelta(days=30)).strftime('%d/%m/%Y')
        return """1. ราคาดังกล่าวข้างต้นยืนยันราคาถึงวันที่ %s
2. หากมีการเปลี่ยนแปลงรายการใดๆ ข้างต้น จะต้องแจ้งให้บริษัทฯ ทราบล่วงหน้าไม่น้อยกว่า 30 วัน ก่อนส่งสินค้า
3. สามารถทยอยส่งสินค้าได้ 60 วัน หลังจากได้รับเอกสารยืนยันการสั่งซื้อ
4. ระยะทางการยกของให้สูงสุดไม่เกินระยะทาง 25 เมตร จากจุดจอดรถ
5. ทางเดินต้องกว้างพอให้สามารถยกของได้ 2 คนต่อกล่อง
6. ราคาสินค้าไม่รวมบริการติดตั้ง
7. ราคาเสนอถึงโครงการ %s""" % (expiry_date, self.project_name or '')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if 'terms_conditions' in fields:
            res['terms_conditions'] = self._get_terms_conditions()
        return res

    @api.onchange('project_name')
    def _onchange_project_name(self):
        self.terms_conditions = self._get_terms_conditions()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('quotation_no') or vals.get('quotation_no') == '':
                sequence = self.env['ir.sequence'].next_by_code('sale.quotation')
                if sequence:
                    vals['quotation_no'] = sequence
        records = super().create(vals_list)
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'project_name' in vals:
            self.terms_conditions = self._get_terms_conditions()
        return result

    @property
    def terms_and_conditions_report(self):
        self.ensure_one()
        return self.payment_term_id.note or self.terms_conditions or ''