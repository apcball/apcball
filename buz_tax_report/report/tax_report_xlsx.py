# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class TaxReportXlsx(models.AbstractModel):
    _name = 'report.buz_tax_report.tax_report_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Tax Report XLSX'

    def generate_xlsx_report(self, workbook, data, objects):
        """Generate the Excel report for tax information"""
        
        # Get wizard data - handle both data formats
        if data and 'form' in data:
            wizard_data = data['form']
            wizard_id = wizard_data.get('id')
            if wizard_id:
                wizard = self.env['tax.report.wizard'].browse(wizard_id)
            else:
                # Create temporary wizard object from form data
                wizard = self.env['tax.report.wizard'].new(wizard_data)
        elif objects:
            wizard = objects[0]
        else:
            return
            
        date_from = wizard.date_from
        date_to = wizard.date_to
        company_id = wizard.company_id.id
        display_details = wizard.display_details
        tax_type = wizard.tax_type
        
        # Create worksheet
        sheet_name = _('Tax Report (Detailed)') if display_details else _('Tax Report')
        sheet = workbook.add_worksheet(sheet_name)
        
        # Define formats
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D7E4BC',
            'border': 1
        })
        
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#F2F2F2',
            'border': 1,
            'text_wrap': True
        })
        
        data_format = workbook.add_format({
            'font_size': 10,
            'valign': 'vcenter',
            'border': 1,
            'text_wrap': True
        })
        
        number_format = workbook.add_format({
            'font_size': 10,
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0.00'
        })
        
        date_format = workbook.add_format({
            'font_size': 10,
            'valign': 'vcenter',
            'border': 1,
            'num_format': 'dd/mm/yyyy'
        })
        
        if display_details:
            # Set column widths for detailed view
            sheet.set_column('A:A', 5)   # No.
            sheet.set_column('B:B', 20)  # Tax Name
            sheet.set_column('C:C', 15)  # Tax Type
            sheet.set_column('D:D', 12)  # Rate
            sheet.set_column('E:E', 15)  # Base Amount
            sheet.set_column('F:F', 15)  # Tax Amount
            sheet.set_column('G:G', 12)  # Date
            sheet.set_column('H:H', 20)  # Document Reference
            sheet.set_column('I:I', 20)  # Partner Name
            sheet.set_column('J:J', 30)  # Description
            
            # Write title
            sheet.merge_range('A1:J2', f'{wizard.company_id.name}\nTax Report (Detailed)', title_format)
            
            # Write period
            sheet.merge_range('A3:J3', 
                             f'Period: {date_from.strftime("%d/%m/%Y") if date_from else ""} - {date_to.strftime("%d/%m/%Y") if date_to else ""}', 
                             header_format)
            
            # Write headers
            headers = [
                _('No.'),
                _('Tax Name'),
                _('Tax Type'),
                _('Rate (%)'),
                _('Base Amount'),
                _('Tax Amount'),
                _('Date'),
                _('Document Reference'),
                _('Partner'),
                _('Description')
            ]
        else:
            # Set column widths for summary view
            sheet.set_column('A:A', 5)   # No.
            sheet.set_column('B:B', 20)  # Tax Name
            sheet.set_column('C:C', 15)  # Tax Type
            sheet.set_column('D:D', 12)  # Rate
            sheet.set_column('E:E', 15)  # Base Amount
            sheet.set_column('F:F', 15)  # Tax Amount
            sheet.set_column('G:G', 12)  # Count
            
            # Write title
            sheet.merge_range('A1:G2', f'{wizard.company_id.name}\nTax Report (Summary)', title_format)
            
            # Write period
            sheet.merge_range('A3:G3', 
                             f'Period: {date_from.strftime("%d/%m/%Y") if date_from else ""} - {date_to.strftime("%d/%m/%Y") if date_to else ""}', 
                             header_format)
            
            # Write headers
            headers = [
                _('No.'),
                _('Tax Name'),
                _('Tax Type'),
                _('Rate (%)'),
                _('Base Amount'),
                _('Tax Amount'),
                _('Count')
            ]
        
        row = 4
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)
        
        row += 1
        
        # Get tax data
        specific_tax_ids = wizard.specific_tax_ids.ids if hasattr(wizard, 'specific_tax_ids') and wizard.specific_tax_ids else None
        tax_data = self._get_tax_data(date_from, date_to, company_id, tax_type, display_details, specific_tax_ids)
        
        # Write data
        line_no = 1
        total_base = 0.0
        total_tax = 0.0
        
        for tax_line in tax_data:
            sheet.write(row, 0, line_no, data_format)
            sheet.write(row, 1, tax_line.get('tax_name', ''), data_format)
            sheet.write(row, 2, tax_line.get('tax_type', ''), data_format)
            sheet.write(row, 3, tax_line.get('tax_rate', 0.0), number_format)
            sheet.write(row, 4, tax_line.get('base_amount', 0.0), number_format)
            sheet.write(row, 5, tax_line.get('tax_amount', 0.0), number_format)
            
            if display_details:
                sheet.write(row, 6, tax_line.get('date', ''), date_format)
                sheet.write(row, 7, tax_line.get('reference', ''), data_format)
                sheet.write(row, 8, tax_line.get('partner_name', ''), data_format)
                sheet.write(row, 9, tax_line.get('description', ''), data_format)
            else:
                sheet.write(row, 6, tax_line.get('count', 0), data_format)
            
            total_base += tax_line.get('base_amount', 0.0)
            total_tax += tax_line.get('tax_amount', 0.0)
            
            row += 1
            line_no += 1
        
        # Write totals
        total_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#E6E6E6',
            'num_format': '#,##0.00'
        })
        
        total_label_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#E6E6E6'
        })
        
        if display_details:
            sheet.merge_range(f'A{row+1}:D{row+1}', _('TOTAL'), total_label_format)
            sheet.write(row, 4, total_base, total_format)
            sheet.write(row, 5, total_tax, total_format)
            for col in range(6, 10):
                sheet.write(row, col, '', total_label_format)
        else:
            sheet.merge_range(f'A{row+1}:D{row+1}', _('TOTAL'), total_label_format)
            sheet.write(row, 4, total_base, total_format)
            sheet.write(row, 5, total_tax, total_format)
            sheet.write(row, 6, '', total_label_format)

    def _get_tax_data(self, date_from, date_to, company_id, tax_type='all', display_details=False, specific_tax_ids=None):
        """Get tax data from account move lines"""
        
        domain = [
            ('company_id', '=', company_id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('tax_line_id', '!=', False),
            ('move_id.state', '=', 'posted')
        ]
        
        # Filter by tax type if specified
        if tax_type == 'sale':
            domain.append(('tax_line_id.type_tax_use', '=', 'sale'))
        elif tax_type == 'purchase':
            domain.append(('tax_line_id.type_tax_use', '=', 'purchase'))
        
        # Filter by specific taxes if provided
        if specific_tax_ids:
            domain.append(('tax_line_id', 'in', specific_tax_ids))
        
        # Fetch only the fields we need to avoid potential conflicts
        move_lines = self.env['account.move.line'].search_read(
            domain, 
            ['id', 'tax_line_id', 'balance', 'date', 'name', 'partner_id', 'move_id'],
            order='date, move_id'
        )
        
        if display_details:
            # Return detailed data for each line
            tax_data = []
            for line_data in move_lines:
                if line_data['tax_line_id']:
                    # Get tax information
                    tax = self.env['account.tax'].browse(line_data['tax_line_id'][0])
                    partner = self.env['res.partner'].browse(line_data['partner_id'][0]) if line_data['partner_id'] else None
                    move = self.env['account.move'].browse(line_data['move_id'][0])
                    
                    tax_type_label = 'Sale' if tax.type_tax_use == 'sale' else 'Purchase'
                    
                    # Get base amount from the related base lines
                    base_amount = 0.0
                    base_lines_data = self.env['account.move.line'].search_read([
                        ('move_id', '=', line_data['move_id'][0]),
                        ('tax_ids', 'in', [tax.id])
                    ], ['balance'])
                    for base_line_data in base_lines_data:
                        base_amount += abs(base_line_data['balance'])
                    
                    tax_data.append({
                        'tax_name': tax.name,
                        'tax_type': tax_type_label,
                        'tax_rate': tax.amount,
                        'base_amount': base_amount,
                        'tax_amount': abs(line_data['balance']),
                        'date': line_data['date'],
                        'reference': move.name or '',
                        'partner_name': partner.name if partner else '',
                        'description': line_data['name'] or ''
                    })
        else:
            # Return summarized data grouped by tax
            tax_summary = {}
            for line_data in move_lines:
                if line_data['tax_line_id']:
                    # Get tax information
                    tax = self.env['account.tax'].browse(line_data['tax_line_id'][0])
                    tax_key = (tax.id, tax.name, tax.type_tax_use, tax.amount)
                    
                    if tax_key not in tax_summary:
                        tax_summary[tax_key] = {
                            'tax_name': tax.name,
                            'tax_type': 'Sale' if tax.type_tax_use == 'sale' else 'Purchase',
                            'tax_rate': tax.amount,
                            'base_amount': 0.0,
                            'tax_amount': 0.0,
                            'count': 0
                        }
                    
                    # Get base amount from the related base lines
                    base_amount = 0.0
                    base_lines_data = self.env['account.move.line'].search_read([
                        ('move_id', '=', line_data['move_id'][0]),
                        ('tax_ids', 'in', [tax.id])
                    ], ['balance'])
                    for base_line_data in base_lines_data:
                        base_amount += abs(base_line_data['balance'])
                    
                    tax_summary[tax_key]['base_amount'] += base_amount
                    tax_summary[tax_key]['tax_amount'] += abs(line_data['balance'])
                    tax_summary[tax_key]['count'] += 1
            
            tax_data = list(tax_summary.values())
        
        return tax_data
