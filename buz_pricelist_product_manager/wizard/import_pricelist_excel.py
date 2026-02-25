from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
import json

try:
    import openpyxl
except ImportError:
    openpyxl = None

class ImportPricelistExcel(models.TransientModel):
    _name = 'import.pricelist.excel'
    _description = 'Import Pricelist Excel'

    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', required=True)
    file_data = fields.Binary('File', required=True)
    file_name = fields.Char('File Name')
    
    state = fields.Selection([
        ('upload', 'Upload'),
        ('preview', 'Preview')
    ], default='upload', string='State')
    
    preview_ids = fields.One2many('import.pricelist.preview', 'wizard_id', string='Preview Lines')

    def action_preview(self):
        if not openpyxl:
             raise UserError(_("Python module 'openpyxl' is required."))
             
        self.ensure_one()
        self.preview_ids.unlink() # Clear previous
        
        try:
            file_content = base64.b64decode(self.file_data)
            wb = openpyxl.load_workbook(filename=io.BytesIO(file_content), read_only=True, data_only=True)
            ws = wb.active
        except Exception as e:
            raise UserError(_("Invalid file format: %s") % str(e))
            
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise UserError(_("File is empty"))
            
        headers = rows[0]
        # Added installation_price
        required_headers = ['pricelist', 'product_name', 'variant', 'category', 'base_price', 'rule_type', 'price', 'installation_price', 'min_qty', 'date_start', 'date_end']
        
        header_map = {h: i for i, h in enumerate(headers) if h}
        
        missing = [h for h in required_headers if h not in header_map]
        
        # Check for product identifier
        product_code_header = 'Internal Reference' if 'Internal Reference' in header_map else 'product_code'
        if product_code_header not in header_map:
             missing.append('Internal Reference (or product_code)')

        if missing:
             raise UserError(_("Missing columns: %s") % ', '.join(missing))
            
        preview_lines = []
        
        # Batch Optimization: Collect codes
        data_rows = rows[1:]
        all_codes = {row[header_map[product_code_header]] for row in data_rows if row[header_map[product_code_header]]}
        
        # Batch Optimization: Fetch Products
        products = self.env['product.product'].search([('default_code', 'in', list(all_codes))])
        product_map = {p.default_code: p for p in products}
        
        # Batch Optimization: Fetch Existing Rules (Variant Level)
        existing_rules = self.env['product.pricelist.item'].search([
            ('pricelist_id', '=', self.pricelist_id.id),
            ('product_id', 'in', products.ids)
        ])
        rule_map = {(r.product_id.id, r.min_quantity or 0.0): r for r in existing_rules}

        # Batch Optimization: Fetch Existing Rules (Template Level)
        # Needed to find rules that apply to the product via its template if no specific variant rule exists
        product_tmpl_ids = products.mapped('product_tmpl_id').ids
        existing_tmpl_rules = self.env['product.pricelist.item'].search([
            ('pricelist_id', '=', self.pricelist_id.id),
            ('product_tmpl_id', 'in', product_tmpl_ids),
            ('product_id', '=', False) 
        ])
        rule_map_tmpl = {(r.product_tmpl_id.id, r.min_quantity or 0.0): r for r in existing_tmpl_rules}

        # Iterate rows
        for idx, row in enumerate(data_rows, start=1):
            row_dict = {}
            for h in required_headers:
                row_dict[h] = row[header_map[h]]
            row_dict[product_code_header] = row[header_map[product_code_header]]
            
            # 1. Validate Pricelist
            row_pricelist = row_dict.get('pricelist')
            if row_pricelist and row_pricelist != self.pricelist_id.name:
                preview_lines.append({
                    'wizard_id': self.id,
                    'status': 'error',
                    'action': 'error',
                    'error_message': f"Pricelist mismatch: '{row_pricelist}' vs '{self.pricelist_id.name}'"
                })
                continue
                
            # 2. Find Product
            product_code = row_dict.get(product_code_header)
            product = product_map.get(product_code)
            
            if not product:
                preview_lines.append({
                    'wizard_id': self.id,
                    'product_xml_id': product_code,
                    'status': 'error',
                    'action': 'error',
                    'error_message': "Product not found"
                })
                continue

            # 3. Find Rule
            try:
                min_qty = float(row_dict.get('min_qty') or 0.0)
            except (ValueError, TypeError):
                min_qty = 0.0
            
            # Lookup in batch map (Variant)
            rule = rule_map.get((product.id, min_qty))
            
            # If not found, Lookup in batch map (Template)
            if not rule:
                 rule = rule_map_tmpl.get((product.product_tmpl_id.id, min_qty))
            
            new_price = row_dict.get('price')
            new_install_price = row_dict.get('installation_price')
            
            # Parse Dates
            date_start = row_dict.get('date_start')
            date_end = row_dict.get('date_end')
            
            status = 'ok'
            action = 'skip'
            error_msg = ''
            
            # Validate Prices
            if not isinstance(new_price, (int, float)) or new_price < 0:
                status = 'error'
                action = 'error'
                error_msg = "Invalid Price"

            if (new_install_price is not None) and (not isinstance(new_install_price, (int, float)) or new_install_price < 0):
                 status = 'error'
                 action = 'error'
                 error_msg = "Invalid Installation Price"
            if new_install_price is None:
                new_install_price = 0.0
            
            old_price = 0.0
            old_install_price = 0.0

            if status == 'ok':
                if rule and rule.compute_price == 'fixed':
                    old_price = rule.fixed_price
                else:
                    old_price = self.pricelist_id._get_product_price(
                        product, 
                        quantity=min_qty or 1.0,
                        date=fields.Datetime.now()
                    )
                
                if rule:
                    old_install_price = rule.installation_price
                    current_price = rule.fixed_price if rule.compute_price == 'fixed' else old_price
                    
                    price_changed = abs(current_price - new_price) > 0.001
                    install_changed = abs(old_install_price - new_install_price) > 0.001
                    
                    if price_changed or install_changed:
                        action = 'update'
                    else:
                        action = 'skip'
                else:
                    action = 'create'
            
            preview_lines.append({
                'wizard_id': self.id,
                'product_id': product.id,
                'product_xml_id': product_code,
                'product_name': product.name,
                'old_price': old_price,
                'new_price': new_price,
                'old_installation_price': old_install_price,
                'new_installation_price': new_install_price,
                'min_qty': min_qty,
                'action': action,
                'status': status,
                'error_message': error_msg,
                'rule_id': rule.id if rule else False,
                'row_data': json.dumps({
                    'price': new_price,
                    'installation_price': new_install_price,
                    'date_start': str(date_start) if date_start else False, 
                    'date_end': str(date_end) if date_end else False, 
                    'min_qty': min_qty, 
                    'rule_type': row_dict.get('rule_type')
                })
            })
            
        self.env['import.pricelist.preview'].create(preview_lines)
        self.state = 'preview'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'import.pricelist.excel',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_import(self):
        self.ensure_one()
        valid_lines = self.preview_ids.filtered(lambda l: l.status != 'error' and l.action != 'skip')
        
        updated = 0
        created = 0
        
        # Separate Create and Update
        create_lines = valid_lines.filtered(lambda l: l.action == 'create')
        update_lines = valid_lines.filtered(lambda l: l.action == 'update')
        
        rule_type_map = {'fixed': 'fixed', 'percentage': 'percentage', 'formula': 'formula'}
        
        # Batch Create
        to_create_vals = []
        for line in create_lines:
            data = json.loads(line.row_data)
            vals = {
                'pricelist_id': self.pricelist_id.id,
                'product_id': line.product_id.id,
                'applied_on': '0_product_variant',
                'compute_price': rule_type_map.get(data.get('rule_type'), 'fixed'),
                'fixed_price': data['price'],
                'installation_price': data.get('installation_price', 0.0),
                'min_quantity': data['min_qty'],
                'date_start': data['date_start'] if data['date_start'] else False,
                'date_end': data['date_end'] if data['date_end'] else False,
            }
            to_create_vals.append(vals)
            
        if to_create_vals:
            self.env['product.pricelist.item'].create(to_create_vals)
            created = len(to_create_vals)
        
        # Update Loop
        for line in update_lines:
            data = json.loads(line.row_data)
            vals = {
                'fixed_price': data['price'],
                'installation_price': data.get('installation_price', 0.0),
                'min_quantity': data['min_qty'],
                'date_start': data['date_start'] if data['date_start'] else False,
                'date_end': data['date_end'] if data['date_end'] else False,
            }
            
            if data.get('rule_type') in rule_type_map:
                vals['compute_price'] = rule_type_map[data['rule_type']]
            
            line.rule_id.write(vals)
            updated += 1
        
        skipped = len(self.preview_ids) - updated - created
        
        # Create Log
        self.env['pricelist.import.log'].create({
            'pricelist_id': self.pricelist_id.id,
            'total_rows': len(self.preview_ids),
            'updated_count': updated,
            'created_count': created,
            'skipped_count': skipped,
            'file_name': self.file_name
        })
        
        return {'type': 'ir.actions.act_window_close'}
