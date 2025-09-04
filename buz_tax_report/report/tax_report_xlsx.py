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
            'font_size': 18,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D7E4BC',
            'border': 1
        })
        
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
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
            'num_format': '#,##0.00',
            'align': 'right'
        })
        
        date_format = workbook.add_format({
            'font_size': 10,
            'valign': 'vcenter',
            'border': 1,
            'num_format': 'dd/mm/yyyy',
            'align': 'center'
        })
        
        if display_details:
            # Set column widths for detailed view (reordered to match requested layout)
            # Column widths tuned to match the visual in the provided screenshot
            sheet.set_column('A:A', 7)   # No.
            sheet.set_column('B:B', 12)  # Date
            sheet.set_column('C:C', 22)  # Document Reference
            sheet.set_column('D:D', 32)  # Partner Name
            sheet.set_column('E:E', 10)  # Tax Rate
            sheet.set_column('F:F', 18)  # Tax ID/VAT
            # Removed Establishment column
            sheet.set_column('G:G', 18)  # Base Amount
            sheet.set_column('H:H', 14)  # Tax Amount
            sheet.set_column('I:I', 14)  # Total Amount (Base + Tax)
            # Hide any extra columns to avoid stray empty fields showing in Excel
            sheet.set_column('J:Z', 2)

            # Write title (company name + custom report name)
            # Prefer explicit report_name from wizard/config. If missing, use tax_type->Thai name.
            if getattr(wizard, 'report_name', False):
                base_title = wizard.report_name
            else:
                if wizard.tax_type == 'purchase':
                    base_title = _('รายงานภาษีซื้อ')
                elif wizard.tax_type == 'sale':
                    base_title = _('รายงานภาษีขาย')
                else:
                    base_title = _('รายงานภาษี')
            # Append localized detail/summary suffix
            suffix = _('(Detailed)') if display_details else _('(Summary)')
            report_title = f"{base_title} {suffix}" if suffix not in (base_title or '') else base_title
            sheet.merge_range('A1:I2', "%s\n%s" % (wizard.company_id.name or '', report_title), title_format)

            # Write period in Thai-style label
            period_label = _('เดือนภาษี')
            period_value = ''
            if date_from and date_to:
                # Try to show month name and year from date_from
                try:
                    period_value = f"{date_from.strftime('%B')} {date_from.year}"
                except Exception:
                    period_value = f"{date_from} - {date_to}"
            sheet.merge_range('A3:I3', f"{period_label} {period_value}", header_format)

            # Write headers in the desired order
            headers = [
                _('ลำดับ'),
                _('วันที่'),
                _('เลขที่เอกสาร'),
                _('ชื่อผู้ขายสินค้า/ผู้ให้บริการ'),
                _('อัตรา (%)'),
                _('เลขประจำตัวผู้เสียภาษี'),
                # removed establishment header
                _('มูลค่าสินค้า/บริการ (ไม่รวมภาษี)'),
                _('จำนวนเงินภาษี'),
                _('จำนวนเงินรวม')
            ]
        else:
            # Set column widths for summary view
            sheet.set_column('A:A', 7)   # No.
            sheet.set_column('B:B', 20)  # Tax Name
            sheet.set_column('C:C', 15)  # Tax Type
            sheet.set_column('D:D', 12)  # Rate
            sheet.set_column('E:E', 15)  # Base Amount
            sheet.set_column('F:F', 15)  # Tax Amount
            sheet.set_column('G:G', 15)  # Total Amount (Base + Tax)
            sheet.set_column('H:H', 12)  # Count
            # Hide extra columns for summary view as well
            sheet.set_column('I:Z', 2)
            # Prepare title and period (compute before writing merged ranges)
            if getattr(wizard, 'report_name', False):
                base_title = wizard.report_name
            else:
                if wizard.tax_type == 'purchase':
                    base_title = _('รายงานภาษีซื้อ')
                elif wizard.tax_type == 'sale':
                    base_title = _('รายงานภาษีขาย')
                else:
                    base_title = _('รายงานภาษี')
            suffix = _('(Detailed)') if display_details else _('(Summary)')
            report_title = f"{base_title} {suffix}" if suffix not in (base_title or '') else base_title

            period_label = _('เดือนภาษี')
            period_value = ''
            if date_from and date_to:
                try:
                    period_value = f"{date_from.strftime('%B')} {date_from.year}"
                except Exception:
                    period_value = f"{date_from} - {date_to}"

            # Write title and period
            sheet.merge_range('A1:G2', "%s\n%s" % (wizard.company_id.name or '', report_title), title_format)
            sheet.merge_range('A3:G3', f"{period_label} {period_value}", header_format)

            # Write headers
            headers = [
                _('ลำดับ'),
                _('ชื่อภาษี'),
                _('ประเภทภาษี'),
                _('อัตรา (%)'),
                _('มูลค่า (ไม่รวมภาษี)'),
                _('จำนวนเงินภาษี'),
                _('จำนวนรายการ')
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
            # Reordered write for detailed view
            sheet.write(row, 0, line_no, data_format)
            if display_details:
                    # Date
                    sheet.write(row, 1, tax_line.get('date', ''), date_format)
                    # Document Reference
                    sheet.write(row, 2, tax_line.get('reference', ''), data_format)
                    # Partner Name
                    sheet.write(row, 3, tax_line.get('partner_name', ''), data_format)
                    # Tax Rate (show like '7%')
                    rate = tax_line.get('tax_rate', 0.0)
                    try:
                        rate_val = float(rate)
                        rate_str = f"{int(rate_val)}%" if rate_val.is_integer() else f"{rate_val}%"
                    except Exception:
                        rate_str = str(rate)
                    sheet.write(row, 4, rate_str, data_format)
                    # Partner VAT / Tax ID
                    sheet.write(row, 5, tax_line.get('partner_vat', ''), data_format)
                    # Base & Tax amounts (establishment removed)
                    sheet.write(row, 6, tax_line.get('base_amount', 0.0), number_format)
                    sheet.write(row, 7, tax_line.get('tax_amount', 0.0), number_format)
                    # Total = base + tax
                    total_line = (tax_line.get('base_amount', 0.0) or 0.0) + (tax_line.get('tax_amount', 0.0) or 0.0)
                    sheet.write(row, 8, total_line, number_format)
            else:
                # Summary view unchanged
                sheet.write(row, 1, tax_line.get('tax_name', ''), data_format)
                sheet.write(row, 2, tax_line.get('tax_type', ''), data_format)
                sheet.write(row, 3, tax_line.get('tax_rate', 0.0), number_format)
                sheet.write(row, 4, tax_line.get('base_amount', 0.0), number_format)
                sheet.write(row, 5, tax_line.get('tax_amount', 0.0), number_format)
                sheet.write(row, 6, tax_line.get('count', 0), data_format)

            total_base += tax_line.get('base_amount', 0.0)
            total_tax += tax_line.get('tax_amount', 0.0)
            # accumulate totals for the new total column as base + tax

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
            # Merge label across first 7 columns (No. through Establishment)
            sheet.merge_range(f'A{row+1}:F{row+1}', _('TOTAL'), total_label_format)
            # Base Amount column is index 6, Tax Amount is index 7, Total Amount is index 8
            sheet.write(row, 6, total_base, total_format)
            sheet.write(row, 7, total_tax, total_format)
            sheet.write(row, 8, total_base + total_tax, total_format)
            for col in range(0, 6):
                sheet.write(row, col, '', total_label_format)
        else:
            sheet.merge_range(f'A{row+1}:D{row+1}', _('TOTAL'), total_label_format)
            sheet.write(row, 4, total_base, total_format)
            sheet.write(row, 5, total_tax, total_format)
            sheet.write(row, 6, total_base + total_tax, total_format)
            sheet.write(row, 7, '', total_label_format)

    def _get_tax_data(self, date_from, date_to, company_id, tax_type='all', display_details=False, specific_tax_ids=None):
        """Get tax data from account move lines"""
        
        # For purchase tax, we should query directly from tax invoice records within date range
        if tax_type == 'purchase':
            # Query tax invoice records directly for purchase tax
            tax_invoice_domain = [
                ('company_id', '=', company_id),
                ('tax_invoice_date', '>=', date_from),
                ('tax_invoice_date', '<=', date_to),
                ('tax_line_id.type_tax_use', '=', 'purchase'),
                ('move_id.state', '=', 'posted'),
                ('move_line_id', '!=', False)  # Ensure we have a valid move line
            ]
            
            # Filter by specific taxes if provided
            if specific_tax_ids:
                tax_invoice_domain.append(('tax_line_id', 'in', specific_tax_ids))
            
            tax_invoices = self.env['account.move.tax.invoice'].search(tax_invoice_domain, order='tax_invoice_date, move_id')
            
            # Debug: log the number of tax invoices found
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Found {len(tax_invoices)} tax invoice records for purchase tax in date range {date_from} to {date_to}")
            
            # Convert tax invoice records to move line format for compatibility
            move_lines = []
            for tax_inv in tax_invoices:
                if tax_inv.move_line_id:
                    move_lines.append({
                        'id': tax_inv.move_line_id.id,
                        'tax_line_id': [tax_inv.tax_line_id.id, tax_inv.tax_line_id.name] if tax_inv.tax_line_id else False,
                        'balance': tax_inv.balance or 0.0,
                        'date': tax_inv.tax_invoice_date or tax_inv.move_line_id.date,
                        'name': tax_inv.move_line_id.name or '',
                        'partner_id': [tax_inv.partner_id.id, tax_inv.partner_id.name] if tax_inv.partner_id else False,
                        'move_id': [tax_inv.move_id.id, tax_inv.move_id.name] if tax_inv.move_id else False,
                        'tax_invoice_record': tax_inv  # Keep reference to original tax invoice
                    })
            
        else:
            # For sale and 'all', use standard move line filtering
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
            
            # Filter by specific taxes if provided
            if specific_tax_ids:
                domain.append(('tax_line_id', 'in', specific_tax_ids))
            
            # Fetch move lines
            move_lines = self.env['account.move.line'].search_read(
                domain, 
                ['id', 'tax_line_id', 'balance', 'date', 'name', 'partner_id', 'move_id'],
                order='date, move_id'
            )
        
        # Filter by specific taxes if provided - this is now handled above for purchase
        # if specific_tax_ids:
        #     if tax_type == 'purchase':
        #         # For purchase, filter the tax_invoices result
        #         tax_invoices = tax_invoices.filtered(lambda t: t.tax_line_id.id in specific_tax_ids)
        #         move_line_ids = tax_invoices.mapped('move_line_id.id')
        #         move_lines = self.env['account.move.line'].search_read([
        #             ('id', 'in', move_line_ids),
        #             ('tax_line_id', '!=', False)
        #         ], ['id', 'tax_line_id', 'balance', 'date', 'name', 'partner_id', 'move_id'],
        #         order='date, move_id')
        #     else:
        #         # For sale/all, add to domain
        #         domain.append(('tax_line_id', 'in', specific_tax_ids))
        #         move_lines = self.env['account.move.line'].search_read(
        #             domain, 
        #             ['id', 'tax_line_id', 'balance', 'date', 'name', 'partner_id', 'move_id'],
        #             order='date, move_id'
        #         )
        
        # Fetch only the fields we need to avoid potential conflicts
        # move_lines = self.env['account.move.line'].search_read(
        #     domain, 
        #     ['id', 'tax_line_id', 'balance', 'date', 'name', 'partner_id', 'move_id'],
        #     order='date, move_id'
        # )
        # Prefetch tax-invoice records related to these move lines to avoid per-line searches
        move_line_ids = [ml['id'] for ml in move_lines]
        move_ids = [ml['move_id'][0] for ml in move_lines if ml.get('move_id')]
        taxinv_map_by_move_line = {}
        taxinv_map_by_move_and_tax = {}
        if move_line_ids or move_ids:
            try:
                taxinv_domain = []
                if move_ids and move_line_ids:
                    taxinv_domain = ['|', ('move_id', 'in', move_ids), ('move_line_id', 'in', move_line_ids)]
                elif move_line_ids:
                    taxinv_domain = [('move_line_id', 'in', move_line_ids)]
                elif move_ids:
                    taxinv_domain = [('move_id', 'in', move_ids)]

                taxinv_records = self.env['account.move.tax.invoice'].search(taxinv_domain)
                for tiv in taxinv_records:
                    # map by move_line_id when available (preferred)
                    if tiv.move_line_id:
                        taxinv_map_by_move_line[tiv.move_line_id.id] = tiv
                    # also map by (move_id, tax_line_id) as a fallback
                    if tiv.move_id and tiv.tax_line_id:
                        taxinv_map_by_move_and_tax[(tiv.move_id.id, tiv.tax_line_id.id)] = tiv
            except Exception:
                # If the localization module isn't installed or model missing, silently continue
                taxinv_map_by_move_line = {}
                taxinv_map_by_move_and_tax = {}
        
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
                    
                    # Try to get an 'establishment' / branch code where available (best-effort)
                    establishment = ''
                    if partner:
                        # Thai localization often stores branch in l10n_th_vat_branch or use city/street
                        establishment = getattr(partner, 'l10n_th_vat_branch', '') or partner.city or partner.street or ''

                    # Handle tax invoice info differently for sales vs purchases
                    doc_ref = (getattr(move, 'ref', None) or move.name or '')
                    doc_date = line_data['date']
                    
                    if tax.type_tax_use == 'sale':
                        # For sales, show the invoice number (field 'number') as the document reference
                        # Fallback to move.name if number not set
                        doc_ref = getattr(move, 'number', None) or getattr(move, 'name', '') or doc_ref
                        # Prefer the invoice date if present on move
                        doc_date = getattr(move, 'invoice_date', line_data.get('date'))
                    elif tax.type_tax_use == 'purchase':
                        # For purchases, if we have the tax invoice record directly, use it
                        if 'tax_invoice_record' in line_data:
                            taxinv = line_data['tax_invoice_record']
                            doc_ref = taxinv.tax_invoice_number or doc_ref
                            doc_date = taxinv.tax_invoice_date or doc_date
                        else:
                            # Fallback to mapping lookup
                            taxinv = None
                            ml_id = line_data.get('id')
                            if ml_id and ml_id in taxinv_map_by_move_line:
                                taxinv = taxinv_map_by_move_line.get(ml_id)
                            if not taxinv and (move.id, tax.id) in taxinv_map_by_move_and_tax:
                                taxinv = taxinv_map_by_move_and_tax.get((move.id, tax.id))
                            if taxinv:
                                # For purchases: use tax_invoice_number for document reference
                                doc_ref = taxinv.tax_invoice_number or doc_ref
                                # For purchases: use tax_invoice_date for date
                                if getattr(taxinv, 'tax_invoice_date', False):
                                    doc_date = taxinv.tax_invoice_date

                    tax_data.append({
                        'tax_name': tax.name,
                        'tax_type': tax_type_label,
                        'tax_rate': tax.amount,
                        'base_amount': base_amount,
                        'tax_amount': abs(line_data['balance']),
                        'date': doc_date,
                        'reference': doc_ref,
                        'partner_name': partner.name if partner else '',
                        'partner_vat': partner.vat or '' if partner else '',
                        'establishment': establishment
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
