from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

class ExportPricelistExcel(models.TransientModel):
    _name = 'export.pricelist.excel'
    _description = 'Export Pricelist to Excel'

    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', required=True)
    export_option = fields.Selection([
        ('selected', 'Selected Records'),
        ('all', 'All Products in Pricelist')
    ], string='Export Option', default='all')
    
    file_data = fields.Binary('File')
    file_name = fields.Char('File Name')

    @api.model
    def default_get(self, fields):
        res = super(ExportPricelistExcel, self).default_get(fields)
        if self.env.context.get('active_model') == 'pricelist.product.matrix':
            # Try to get pricelist from context or active_ids
            active_ids = self.env.context.get('active_ids', [])
            if active_ids:
                record = self.env['pricelist.product.matrix'].browse(active_ids[0])
                res['pricelist_id'] = record.pricelist_id.id
        return res

    def action_export(self):
        if not xlsxwriter:
            raise UserError(_("The 'xlsxwriter' python module is not installed."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Pricelist')

        # Formats
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})
        highlight_format = workbook.add_format({'bg_color': '#FFFFCC'}) # Expired or No rule?
        
        headers = [
            'pricelist', 'product_code', 'product_name', 'variant', 'category',
            'base_price', 'rule_type', 'price', 'installation_price', 'min_qty', 'date_start', 'date_end', 'product_id_db'
        ]
        
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        domain = [('pricelist_id', '=', self.pricelist_id.id)]
        if self.export_option == 'selected':
            active_ids = self.env.context.get('active_ids', [])
            if active_ids:
                domain = [('id', 'in', active_ids)]
            else:
                 # Fallback if selected but no ids? 
                 pass
        
        records = self.env['pricelist.product.matrix'].search(domain)
        
        row = 1
        for rec in records:
            # Logic for highlighting: Products without rule or Expired rules
            # We can use conditional formatting or just format the row. 
            row_format = None
            if not rec.rule_id:
                row_format = highlight_format
            elif rec.date_end and rec.date_end < fields.Datetime.now():
                row_format = highlight_format

            # pricelist_id is required field in import validation? Match by name.
            worksheet.write(row, 0, rec.pricelist_id.name, row_format)
            worksheet.write(row, 1, rec.product_variant_id.default_code or '', row_format)
            worksheet.write(row, 2, rec.product_tmpl_id.name, row_format)
            # Variant attributes display name
            worksheet.write(row, 3, rec.product_variant_id.product_template_variant_value_ids.display_name if rec.product_variant_id.product_template_variant_value_ids else '', row_format)
            worksheet.write(row, 4, rec.category_id.name, row_format)
            worksheet.write(row, 5, rec.base_price, row_format)
            
            # Export rule type or default to fixed?
            rule_type_map = {
                'fixed': 'fixed',
                'percentage': 'percentage',
                'formula': 'formula'
            }
            # If no rule, user probably wants to set 'fixed' or match template.
            # We export what we have.
            worksheet.write(row, 6, rule_type_map.get(rec.rule_type, ''), row_format)
            
            # Price: If fixed, show fixed_price. If computed, show computed?
            # Prompt: "Excel Columns ... price". 
            # Prompt: "Apply Logic... rule.write(new_values)".
            # If we export computed price as 'price', and import it as 'fixed_price', we change logic from formula to fixed.
            # Ideally we export the 'fixed_price' if type is fixed, or the factor if percentage.
            # But the requirement only asks for 'price'. 
            # Given "Inline Edit" logic usually maps price -> fixed_price.
            # We will export the raw fixed_price if available, else 0? 
            # Or export the computed_price so user sees what it is?
            # "Inline Edit Rules: If product has no rule -> create new product.pricelist.item".
            # If I export computed price and re-import, I effectively "Fix" the price.
            # Let's export the `price` field from our model which maps to `fixed_price`.
            
            worksheet.write(row, 7, rec.price if rec.rule_type == 'fixed' else 0.0, row_format)
            worksheet.write(row, 8, rec.installation_price, row_format)
            
            worksheet.write(row, 9, rec.min_quantity, row_format)
            worksheet.write(row, 10, rec.date_start, date_format if rec.date_start else row_format)
            worksheet.write(row, 11, rec.date_end, date_format if rec.date_end else row_format)
            # Hidden ID column for easier matching if needed (though prompt relies on product match)
            # Prompt "Business Validation ... Product must exist". "Steps ... product = find_product(row)".
            # So we rely on code/name.
            worksheet.write(row, 12, rec.product_variant_id.id) 

            row += 1

        workbook.close()
        output.seek(0)
        file_content = base64.b64encode(output.read())
        
        self.write({
            'file_data': file_content,
            'file_name': f'Pricelist_{self.pricelist_id.name}_{fields.Date.today()}.xlsx'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'export.pricelist.excel',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

