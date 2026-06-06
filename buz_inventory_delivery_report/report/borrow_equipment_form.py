import re

from odoo import models, api


class BorrowEquipmentFormPDF(models.AbstractModel):
    _name = 'report.buz_inventory_delivery_report.borrow_equip_form_document'
    _description = 'Borrow Equipment Form PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['stock.picking'].browse(docids)

        def get_product_description(product):
            if product and product.description_sale:
                desc = re.sub(r'<[^>]+>', '', product.description_sale).strip()
                return desc
            return ''

        def clean_product_name(product):
            name = product.name or ''
            default_code = getattr(product, 'default_code', False) or ''
            if name.startswith('[ชุด]'):
                name = name.replace('[ชุด]', '', 1).strip()
            if default_code and name.startswith(default_code):
                name = name[len(default_code):].strip()
            name = re.sub(r'^(?=[A-Z0-9._/-]*\d)[A-Z0-9._/-]+(?:\s*\([A-Z0-9._/-]+\))?\s+', '', name).strip()
            if name.startswith('-'):
                name = name[1:].strip()
            if default_code:
                return f"{default_code} {name}"
            return name

        def get_grouped_lines(picking):
            lines = []
            bom_grouped = {}
            normal_lines = []

            for move in picking.move_ids:
                if getattr(move, 'bom_line_id', False) and move.bom_line_id:
                    if getattr(move, 'sale_line_id', False) and move.sale_line_id:
                        group_key = f"sale_{move.sale_line_id.id}"
                        kit_product = move.sale_line_id.product_id
                        kit_uom = move.sale_line_id.product_uom.name
                        sale_line = move.sale_line_id
                    else:
                        group_key = f"bom_{move.bom_line_id.bom_id.id}"
                        kit_product = move.bom_line_id.bom_id.product_tmpl_id
                        kit_uom = kit_product.uom_id.name
                        sale_line = None

                    if group_key not in bom_grouped:
                        bom_grouped[group_key] = {
                            'product': kit_product,
                            'qty': 0.0,
                            'uom': kit_uom,
                            'moves': [],
                            'sale_line_id': sale_line,
                        }
                    bom_grouped[group_key]['moves'].append(move)
                    if bom_grouped[group_key]['qty'] == 0:
                        bl = move.bom_line_id
                        if bl and bl.product_qty:
                            bom_grouped[group_key]['qty'] = move.product_uom_qty / bl.product_qty
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
                code = prod.default_code or ''
                qty_str = '{:,.2f}'.format(data_dict['qty']) if data_dict['qty'] else ''

                sale_line = data_dict.get('sale_line_id')
                if sale_line and sale_line.name:
                    description_picking = sale_line.name
                else:
                    description_picking = prod.description_picking or ''

                lines.append({
                    'type': 'bom',
                    'display_no': str(line_no),
                    'name': clean_product_name(prod),
                    'product': prod,
                    'code': code,
                    'qty': qty_str,
                    'uom': data_dict['uom'] or '',
                    'description_picking': description_picking,
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

        def get_grouped_pages(items, page_size=7):
            pages = []
            current_page = []
            current_count = 0
            i = 0
            while i < len(items):
                item = items[i]
                if item['type'] == 'bom':
                    bom_parent = item
                    components = []
                    j = i + 1
                    while j < len(items) and items[j]['type'] == 'line' and items[j].get('is_component'):
                        components.append(items[j])
                        j += 1
                    group_size = 1 + len(components)
                    if current_count + group_size > page_size and current_page:
                        pages.append(current_page)
                        current_page = []
                        current_count = 0
                    current_page.append(bom_parent)
                    current_page.extend(components)
                    current_count += group_size
                    i = j
                else:
                    if current_count + 1 > page_size and current_page:
                        pages.append(current_page)
                        current_page = []
                        current_count = 0
                    current_page.append(item)
                    current_count += 1
                    i += 1
            if current_page:
                pages.append(current_page)
            return pages

        return {
            'doc_ids': docids,
            'doc_model': 'stock.picking',
            'docs': docs,
            'get_grouped_lines': get_grouped_lines,
            'get_grouped_pages': get_grouped_pages,
            'clean_product_name': clean_product_name,
            'get_product_description': get_product_description,
            'data': data,
        }
