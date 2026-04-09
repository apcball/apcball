# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import io

try:
    import xlsxwriter
    HAS_XLSXWRITER = True
except ImportError:
    HAS_XLSXWRITER = False

def _map_bom_type(val):
    if not val:
        return 'normal'
    val_str = str(val).strip().lower()
    if val_str in ['phantom', 'kit', 'ชุดประกอบ']:
        return 'phantom'
    return 'normal'

class MrpImportController(http.Controller):

    @http.route('/api/v1/mrp/bom/import', type='json', auth='user', methods=['POST'], csrf=False)
    def import_bom(self, **kw):
        data = request.jsonrequest
        if not data or not isinstance(data, list):
            return {'status': 'error', 'message': 'Invalid JSON format. Expected list of BOMs.'}
        
        session = request.env['mrp.import.session'].create({
            'import_type': 'bom',
            'filename': 'API_BOM_Import.json'
        })
        
        for item in data:
            staging = request.env['mrp.bom.staging'].create({
                'session_id': session.id,
                'bom_code': item.get('bom_code', ''),
                'product_default_code': item.get('product_default_code', ''),
                'product_qty': item.get('product_qty', 1.0),
                'bom_type': _map_bom_type(item.get('bom_type')),
            })
            for line in item.get('lines', []):
                request.env['mrp.bom.line.staging'].create({
                    'bom_staging_id': staging.id,
                    'component_default_code': line.get('component_default_code', ''),
                    'quantity': line.get('quantity', 1.0),
                    'uom': line.get('uom'),
                })
        
        session.action_process()
        return {'status': 'success', 'session_id': session.id, 'session_name': session.name}

    @http.route('/api/v1/mrp/mo/import', type='json', auth='user', methods=['POST'], csrf=False)
    def import_mo(self, **kw):
        data = request.jsonrequest
        if not data or not isinstance(data, list):
            return {'status': 'error', 'message': 'Invalid JSON format. Expected list of MOs.'}
        
        session = request.env['mrp.import.session'].create({
            'import_type': 'mo',
            'filename': 'API_MO_Import.json'
        })
        
        for item in data:
            request.env['mrp.mo.staging'].create({
                'session_id': session.id,
                'mo_name': item.get('mo_name', ''),
                'product_default_code': item.get('product_default_code', ''),
                'product_qty': item.get('product_qty', 1.0),
                'bom_code': item.get('bom_code', ''),
                'bom_type': _map_bom_type(item.get('bom_type')),
                'operation_type': item.get('operation_type', ''),
                'work_center': item.get('work_center', ''),
            })
            
        session.action_process()
        return {'status': 'success', 'session_id': session.id, 'session_name': session.name}

    @http.route('/web/mrp/import/template/<string:import_type>', type='http', auth='user', methods=['GET'], csrf=False)
    def download_template(self, import_type, **kw):
        """Download an XLSX import template for BOM or MO."""
        if import_type not in ('bom', 'mo'):
            return request.make_response(
                'Invalid import type. Use "bom" or "mo".',
                headers=[('Content-Type', 'text/plain')],
                status=400
            )

        if not HAS_XLSXWRITER:
            return request.make_response(
                'xlsxwriter library is not installed on this server.',
                headers=[('Content-Type', 'text/plain')],
                status=500
            )

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        
        header_format = wb.add_format({
            'bold': True, 'font_color': 'white', 'bg_color': '#1F4E79', 
            'align': 'center', 'valign': 'vcenter', 'text_wrap': True
        })
        hint_format = wb.add_format({
            'italic': True, 'font_color': '#595959', 'bg_color': '#D9E1F2', 
            'align': 'center', 'valign': 'vcenter', 'text_wrap': True
        })

        if import_type == 'bom':
            filename = 'BOM_Import_Template.xlsx'

            ws_bom = wb.add_worksheet('BOM')
            bom_headers = ['bom_code', 'product_default_code', 'product_qty', 'bom_type', 'version']
            bom_hints = [
                'Unique BOM code (required)',
                'Product internal reference (required)',
                'Quantity to produce (default 1)',
                'Manufacture this product or Kit (default Manufacture this product)',
                'Version label (optional)',
            ]
            _apply_headers_xlsxwriter(ws_bom, bom_headers, bom_hints, header_format, hint_format)
            ws_bom.write_row(2, 0, ['BOM-001', 'PROD-001', 1.0, 'Manufacture this product', 'v1'])

            ws_line = wb.add_worksheet('BOM Lines')
            line_headers = ['bom_code', 'component_default_code', 'quantity', 'uom', 'operation']
            line_hints = [
                'Must match bom_code in BOM sheet (required)',
                'Component internal reference (required)',
                'Component quantity (required)',
                'Unit of measure name (optional)',
                'Operation / work center (optional)',
            ]
            _apply_headers_xlsxwriter(ws_line, line_headers, line_hints, header_format, hint_format)
            ws_line.write_row(2, 0, ['BOM-001', 'COMP-001', 2.0, 'Units', ''])
            ws_line.write_row(3, 0, ['BOM-001', 'COMP-002', 1.0, 'kg', ''])

        else:
            filename = 'MO_Import_Template.xlsx'

            ws_mo = wb.add_worksheet('Manufacturing Orders')
            mo_headers = [
                'mo_name', 'product_default_code', 'product_qty',
                'bom_code', 'bom_type', 'operation_type', 'work_center', 'planned_start_date', 'planned_finish_date',
            ]
            mo_hints = [
                'MO reference name (required)',
                'Product internal reference (required)',
                'Qty to produce (required)',
                'BOM code to apply (optional)',
                'Manufacture this product or Kit (default Manufacture this product)',
                'Operation Type / Picking Type reference (optional)',
                'Work Center reference (optional)',
                'Planned start YYYY-MM-DD HH:MM:SS (optional)',
                'Planned finish YYYY-MM-DD HH:MM:SS (optional)',
            ]
            _apply_headers_xlsxwriter(ws_mo, mo_headers, mo_hints, header_format, hint_format)
            ws_mo.write_row(2, 0, ['MO-001', 'PROD-001', 10.0, 'BOM-001', 'Manufacture this product', 'Manufacturing', 'WC-01', '2024-01-15 08:00:00', '2024-01-16 17:00:00'])

        wb.close()
        buf.seek(0)
        xlsx_data = buf.read()

        return request.make_response(
            xlsx_data,
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
                ('Content-Length', str(len(xlsx_data))),
            ]
        )


def _apply_headers_xlsxwriter(ws, headers, hints, header_format, hint_format):
    """Write styled header row + hint row to a worksheet using xlsxwriter."""
    for col, header in enumerate(headers):
        ws.write(0, col, header, header_format)
        ws.set_column(col, col, max(len(header) + 4, 22))

    for col, hint in enumerate(hints):
        ws.write(1, col, hint, hint_format)

    ws.set_row(1, 40)
