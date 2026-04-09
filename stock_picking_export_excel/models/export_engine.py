import base64
import io
import xlsxwriter
from odoo import models, api, _
from odoo.exceptions import UserError
from datetime import datetime

class ExportEngine(models.AbstractModel):
    _name = 'export.engine'
    _description = 'Export Engine for Stock Picking'

    @api.model
    def get_picking_data(self, picking_ids):
        pickings = self.env['stock.picking'].browse(picking_ids)
        data = []
        for picking in pickings:
            lines = []
            for move in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
                lot_names = move.move_line_ids.mapped('lot_id.name')
                lot_name = ', '.join(filter(None, lot_names))
                
                # Use product_uom_qty for demand, and quantity if it is already done
                if move.state == 'done':
                    qty = move.quantity if hasattr(move, 'quantity') else move.product_uom_qty
                else:
                    qty = move.product_uom_qty

                lines.append({
                    "default_code": move.product_id.default_code or '',
                    "description": move.name or move.product_id.display_name,
                    "scheduled_date": move.date,
                    "qty": qty,
                    "uom": move.product_uom.name,
                    "cost": self.get_fifo_cost(move),
                    "lot": lot_name,
                })
            
            data.append({
                "document": picking.name,
                "type": picking.picking_type_code,
                "date": picking.scheduled_date or picking.date_done,
                "effective_date": picking.date_done,
                "partner": picking.partner_id.name or '',
                "source_location": picking.location_id.complete_name,
                "dest_location": picking.location_dest_id.complete_name,
                "lines": lines
            })
        return data

    @api.model
    def get_fifo_cost(self, move):
        layers = self.env['stock.valuation.layer'].search([('stock_move_id', '=', move.id)])
        if not layers:
            # Fallback for unposted (Ready) moves
            if hasattr(move, 'custom_cost_price') and move.custom_cost_price > 0:
                return move.custom_cost_price
            if hasattr(move, 'price_unit') and move.price_unit > 0:
                return move.price_unit
            return move.product_id.standard_price or 0.0
        total_value = sum(layers.mapped('value'))
        total_qty = sum(layers.mapped('quantity'))
        if total_qty == 0:
            return 0.0
        return abs(total_value / total_qty)

    @api.model
    def generate_excel(self, picking_ids):
        data = self.get_picking_data(picking_ids)
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Stock Transfer')
        
        # Set column widths for better readability
        worksheet.set_column('A:A', 20)  # Document
        worksheet.set_column('B:B', 15)  # Type
        worksheet.set_column('C:D', 20)  # Date, Effective Date
        worksheet.set_column('E:G', 25)  # Partner, Source, Destination
        worksheet.set_column('H:H', 20)  # Product Code
        worksheet.set_column('I:I', 40)  # Description
        worksheet.set_column('J:J', 20)  # Scheduled Date
        worksheet.set_column('K:K', 12)  # Qty
        worksheet.set_column('L:L', 10)  # UOM
        worksheet.set_column('M:M', 15)  # Cost
        worksheet.set_column('N:N', 20)  # Lot
        
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
        cell_format = workbook.add_format({'border': 1})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss', 'border': 1})

        headers = ['Document', 'Type', 'Date', 'Effective Date', 'Partner', 'Source', 'Destination', 
                   'Product Code', 'Description', 'Scheduled Date', 'Qty', 'UOM', 'Cost', 'Lot']
                   
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
            
        row = 1
        for picking in data:
            for line in picking['lines']:
                worksheet.write(row, 0, picking['document'], cell_format)
                worksheet.write(row, 1, picking['type'], cell_format)
                
                # handle datetime timezone naiive issues if necessary
                date_val = picking['date']
                if date_val:
                    worksheet.write_datetime(row, 2, date_val.replace(tzinfo=None), date_format)
                else:
                    worksheet.write(row, 2, '', cell_format)
                    
                eff_date_val = picking['effective_date']
                if eff_date_val:
                    worksheet.write_datetime(row, 3, eff_date_val.replace(tzinfo=None), date_format)
                else:
                    worksheet.write(row, 3, '', cell_format)
                    
                worksheet.write(row, 4, picking['partner'], cell_format)
                worksheet.write(row, 5, picking['source_location'], cell_format)
                worksheet.write(row, 6, picking['dest_location'], cell_format)
                worksheet.write(row, 7, line['default_code'], cell_format)
                worksheet.write(row, 8, line['description'], cell_format)
                
                # Handling scheduled date writing
                if line['scheduled_date']:
                    worksheet.write_datetime(row, 9, line['scheduled_date'].replace(tzinfo=None), date_format)
                else:
                    worksheet.write(row, 9, '', cell_format)
                    
                worksheet.write(row, 10, line['qty'], cell_format)
                worksheet.write(row, 11, line['uom'], cell_format)
                worksheet.write(row, 12, line['cost'], cell_format)
                worksheet.write(row, 13, line['lot'], cell_format)
                row += 1
                
        workbook.close()
        output.seek(0)
        file_data = base64.b64encode(output.read())
        
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"stock_transfer_{date_str}.xlsx"
        
        return file_data, filename
