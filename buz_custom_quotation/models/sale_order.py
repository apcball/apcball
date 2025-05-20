from odoo import api, fields, models
from datetime import timedelta

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    purchase_price = fields.Float(string='Purchase Price', digits='Product Price')

    @api.onchange('product_id')
    def _onchange_product_id_set_purchase_price(self):
        if self.product_id:
            self.purchase_price = self.product_id.standard_price

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    proposal_no = fields.Char(string='Proposal Number', readonly=True, copy=False)
    project_name = fields.Char(string='Project Name')
    customer_name = fields.Char(string='Customer Name')
    terms_conditions = fields.Text(string='Terms and Conditions')

    def _get_terms_conditions(self):
        expiry_date = (fields.Date.today() + timedelta(days=30)).strftime('%d/%m/%Y')
        return """1. ราคาข้างต้นเป็นราคาที่ยังไม่รวมภาษีมูลค่าเพิ่ม 7%% / Above prices are excluded VAT 7%%
2. ราคาอาจมีการเปลี่ยนแปลงโดยไม่ต้องแจ้งให้ทราบล่วงหน้า / Prices are subject to change without prior notice
3. ราคาดังกล่าวข้างต้นยืนยันราคาถึงวันที่ %s
4. หากมีการเปลี่ยนแปลงรายการใดๆ ข้างตั้น จะต้องแจ้งให้บริษัทฯ ทราบล่วงหน้าไม่น้อยกว่า 30 วัน ก่อนส่งสินค้า
5. สามารถทยอยส่งสินค้าได้ 60 วัน หลังจากได้รับเอกสารยืนยันการสังซื้อ
6. ระยะทางการยกของให้สูงสุด ไม่เกินระยะทาง 25 เมตร จากจุดจอดรถ
7. ทางเดินต้องกว้างพอให้สามารถยกของได้ 2 คนต่อกล่อง
8. ราคาสินค้าไม่รวมบริการติดตั้ง
9. ราคาเสนอถึงโครงการ %s""" % (expiry_date, self.project_name or '')

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
            if not vals.get('proposal_no'):
                sequence = self.env['ir.sequence'].next_by_code('sale.proposal')
                if sequence:
                    vals['proposal_no'] = sequence
                elif vals.get('name'):
                    vals['proposal_no'] = vals['name'].replace('SO', 'PS')
        records = super().create(vals_list)
        return records

    def write(self, vals):
        if 'name' in vals and not self.proposal_no:
            sequence = self.env['ir.sequence'].next_by_code('sale.proposal')
            if sequence:
                vals['proposal_no'] = sequence
            else:
                vals['proposal_no'] = vals['name'].replace('SO', 'PS')
        result = super().write(vals)
        if 'project_name' in vals:
            self.terms_conditions = self._get_terms_conditions()
        return result