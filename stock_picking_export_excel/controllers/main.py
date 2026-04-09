import base64
from odoo import http
from odoo.http import request

class StockExportController(http.Controller):
    @http.route('/stock_picking_export/<int:picking_id>', type='http', auth='user')
    def export_picking(self, picking_id, **kwargs):
        picking = request.env['stock.picking'].browse(picking_id)
        if not picking.exists():
            return request.not_found()
            
        file_data, filename = request.env['export.engine'].generate_excel([picking_id])
        
        excel_data = base64.b64decode(file_data)
        
        return request.make_response(
            excel_data,
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )
