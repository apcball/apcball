from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    vehicle_type = fields.Char(string="Vehicle Type")
    def _get_dispatch_report_image_base64(self):
        try:
            from ..report.image_utils import get_dispatch_report_image_base64
            return get_dispatch_report_image_base64()
        except Exception:
            return ''
    vehicle_plate = fields.Char(string="Vehicle Plate")
    driver = fields.Char(string="Driver")
    dispatch_location = fields.Char(string="สถานที่จ่ายสินค้า", compute='_compute_dispatch_location')
    field1 = fields.Char(string="เลขที่ใบขออนุมัติเปลี่ยนสินค้า")
    price_unit = fields.Float(string="ราคาต่อหน่วย")  # เพิ่มราคาต่อหน่วย (unit price)
    price_subtotal = fields.Float(string="จำนวนเงิน", compute='_compute_price_subtotal', store=True)  # คำนวณจำนวนเงิน (subtotal)
    notes = fields.Text(string="หมายเหตุ")  # Add notes field for remarks
    return_reason = fields.Char(string='สาเหตุที่คืน')
    return_doc_no = fields.Char(string='เลขที่เอกสารคืน')
    date_notice = fields.Datetime(string="วันที่แจ้ง")
    date_confirmed = fields.Datetime(string="วันที่ Confirm")
    department_install = fields.Char(string='แผนกติดตั้ง')
    project_name = fields.Char(string="ชื่อโครงการ")
    seller_contact_name = fields.Char(string='ผู้ติดต่อประสานงาน')
    seller_contact_phone = fields.Char(string='เบอร์โทรตัวแทนจำหน่าย')
    project_plot_number = fields.Char(string='เฉพาะโครงการ: เลขที่แปลง')
    house_model = fields.Char(string='แบบบ้าน')
    is_garage = fields.Boolean(string='โรงรถ')
    job_no = fields.Char(string="Job Number")
    sub_district = fields.Char(string='ตำบล')
    employee_contact_id = fields.Many2one('res.partner', string="Employee Contact")
    return_location = fields.Char(string="Return Location")
    request_type = fields.Char(string="ประเภทที่เบิก")
    date_start = fields.Date(string="วันที่เริ่มงาน")

    ship_from_partner_id = fields.Many2one(
        'res.partner', 
        string='Ship From Partner',
        help='Partner representing the place where goods are shipped from'
    )
    
    sale_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        help='ใบสั่งขายที่เกี่ยวข้อง'
    )

    @api.depends('picking_type_id', 'picking_type_id.warehouse_id', 'location_id')
    def _compute_dispatch_location(self):
        """Compute dispatch location from warehouse or location"""
        for picking in self:
            warehouse = None
            # First try to get warehouse from picking type
            if picking.picking_type_id and picking.picking_type_id.warehouse_id:
                warehouse = picking.picking_type_id.warehouse_id
            # If not found, try to get warehouse from source location
            elif picking.location_id:
                warehouse = self.env['stock.warehouse'].search([
                    '|', 
                    ('lot_stock_id', '=', picking.location_id.id),
                    ('view_location_id', 'parent_of', picking.location_id.id)
                ], limit=1)
            
            if warehouse:
                picking.dispatch_location = warehouse.name
            elif picking.location_id:
                picking.dispatch_location = picking.location_id.complete_name
            else:
                picking.dispatch_location = ''

    @api.depends('move_ids.product_uom_qty', 'price_unit')

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
            'doc': self,
            'total_weight': sum(move.product_id.weight * move.product_uom_qty for move in self.move_ids),
            'total_volume': sum(move.product_id.volume * move.product_uom_qty for move in self.move_ids),
            'total_packages': len(self.package_ids),
            'items_per_page': items_per_page,
            'total_items': total_items,
            'total_pages': total_pages,
            'dispatch_image': self._get_dispatch_report_image_base64(),
        }