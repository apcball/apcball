from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    vehicle_type = fields.Char(string="Vehicle Type")
    vehicle_plate = fields.Char(string="Vehicle Plate")
    driver = fields.Char(string="Driver")
    field1 = fields.Char(string="เลขที่ใบขออนุมัติเปลี่ยนสินค้า")
    price_unit = fields.Float(string="ราคาต่อหน่วย")  # เพิ่มราคาต่อหน่วย (unit price)
    price_subtotal = fields.Float(string="จำนวนเงิน", compute='_compute_price_subtotal', store=True)  # คำนวณจำนวนเงิน (subtotal)
    notes = fields.Text(string="หมายเหตุ")  # Add notes field for remarks
    return_reason = fields.Char(string='สาเหตุที่คืน')
    return_doc_no = fields.Char(string='เลขที่เอกสารคืน')

    def _compute_price_subtotal(self):
        for picking in self:
            # Calculate subtotal based on move lines
            picking.price_subtotal = sum(move.product_uom_qty * picking.price_unit for move in picking.move_ids)

    def get_delivery_report_values(self):
        """
        Get additional values for the delivery report
        """
        self.ensure_one()
        
        # Define pagination parameters
        items_per_page = 10  # Number of items per page
        total_items = len(self.move_ids)  # Total number of move lines
        total_pages = (total_items + items_per_page - 1) // items_per_page  # Calculate total pages
        
        return {
            'total_weight': sum(move.product_id.weight * move.product_uom_qty for move in self.move_ids),
            'total_volume': sum(move.product_id.volume * move.product_uom_qty for move in self.move_ids),
            'total_packages': len(self.package_ids),
            'items_per_page': items_per_page,
            'total_items': total_items,
            'total_pages': total_pages,
        }