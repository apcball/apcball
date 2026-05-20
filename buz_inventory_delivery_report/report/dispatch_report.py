# -*- coding: utf-8 -*-
from odoo import models, api


class DispatchReportPDF(models.AbstractModel):
    _name = 'report.buz_inventory_delivery_report.dispatch_report_document'
    _description = 'Dispatch Report PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        """
        Override to ensure proper UTF-8 encoding for Thai language support
        """
        docs = self.env['stock.picking'].browse(docids)
        
        def get_grouped_lines(picking):
            lines = []
            bom_grouped = {}
            normal_lines = []
            
            for move in picking.move_ids:
                if getattr(move, 'bom_line_id', False) and move.bom_line_id:
                    # Group by sale_line_id if available, else bom_id
                    if getattr(move, 'sale_line_id', False) and move.sale_line_id:
                        group_key = f"sale_{move.sale_line_id.id}"
                        kit_product = move.sale_line_id.product_id
                        kit_qty = move.sale_line_id.product_uom_qty
                        kit_uom = move.sale_line_id.product_uom.name
                    else:
                        group_key = f"bom_{move.bom_line_id.bom_id.id}"
                        kit_product = move.bom_line_id.bom_id.product_tmpl_id
                        kit_qty = 0
                        kit_uom = kit_product.uom_id.name

                    if group_key not in bom_grouped:
                        bom_grouped[group_key] = {
                            'product': kit_product,
                            'qty': kit_qty,
                            'uom': kit_uom,
                            'moves': []
                        }
                    bom_grouped[group_key]['moves'].append(move)
                else:
                    normal_lines.append(move)
            
            line_no = 1
            
            for move in normal_lines:
                lines.append({
                    'type': 'line',
                    'display_no': str(line_no),
                    'is_component': False,
                    'move': move,
                })
                line_no += 1
                
            for key, data_dict in bom_grouped.items():
                prod = data_dict['product']
                name = f"[ชุด] {prod.name}"
                code = prod.default_code or ''
                qty_str = '{:,.2f}'.format(data_dict['qty']) if data_dict['qty'] else ''
                
                lines.append({
                    'type': 'bom',
                    'display_no': str(line_no),
                    'name': name,
                    'code': code,
                    'qty': qty_str,
                    'uom': data_dict['uom'] or '',
                })
                line_no += 1
                
                for move in data_dict['moves']:
                    lines.append({
                        'type': 'line',
                        'display_no': '',
                        'is_component': True,
                        'move': move,
                    })
                
            return lines

        return {
            'doc_ids': docids,
            'doc_model': 'stock.picking',
            'docs': docs,
            'get_grouped_lines': get_grouped_lines,
            'data': data,
        }
