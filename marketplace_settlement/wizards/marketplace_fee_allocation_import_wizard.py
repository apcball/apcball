from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import base64
import csv
import io
from odoo.tools.float_utils import float_is_zero


class MarketplaceFeeAllocationImportWizard(models.TransientModel):
    _name = 'marketplace.fee.allocation.import.wizard'
    _description = 'Import Fee Allocation from CSV'

    settlement_id = fields.Many2one('marketplace.settlement', string='Settlement', required=True)
    csv_file = fields.Binary('CSV File', required=True, help='Upload CSV file with fee allocation data')
    csv_filename = fields.Char('CSV Filename')
    import_mode = fields.Selection([
        ('replace', 'Replace Existing Allocations'),
        ('update', 'Update Existing Allocations'),
    ], string='Import Mode', default='replace', required=True)
    
    # CSV format settings
    has_header = fields.Boolean('Has Header Row', default=True)
    delimiter = fields.Selection([
        (',', 'Comma (,)'),
        (';', 'Semicolon (;)'),
        ('\t', 'Tab'),
        ('|', 'Pipe (|)'),
    ], string='Delimiter', default=',', required=True)
    
    # Column mapping
    invoice_column = fields.Integer('Invoice Number Column', default=1, required=True,
                                   help='Column number containing invoice numbers (starting from 1)')
    base_fee_column = fields.Integer('Base Fee Column', default=2,
                                    help='Column number containing base fee amounts (0 = skip)')
    vat_input_column = fields.Integer('VAT Input Column', default=3,
                                     help='Column number containing VAT input amounts (0 = skip)')
    wht_column = fields.Integer('WHT Column', default=4,
                               help='Column number containing withholding tax amounts (0 = skip)')
    
    # Preview data
    preview_data = fields.Text('Preview Data', readonly=True)
    import_summary = fields.Text('Import Summary', readonly=True)

    @api.onchange('csv_file', 'delimiter', 'has_header')
    def _onchange_csv_preview(self):
        """Generate preview of CSV data"""
        if not self.csv_file:
            self.preview_data = ""
            return
        
        try:
            csv_data = base64.b64decode(self.csv_file).decode('utf-8')
            csv_reader = csv.reader(io.StringIO(csv_data), delimiter=self.delimiter)
            
            preview_lines = []
            for i, row in enumerate(csv_reader):
                if i >= 5:  # Show only first 5 rows
                    break
                    
                preview_lines.append(' | '.join(row))
            
            self.preview_data = '\n'.join(preview_lines)
            
        except Exception as e:
            self.preview_data = f"Error reading CSV: {str(e)}"

    def action_import_allocations(self):
        """Import fee allocations from CSV file"""
        self.ensure_one()
        
        if not self.csv_file:
            raise UserError(_("Please upload a CSV file"))
        
        if not self.settlement_id:
            raise UserError(_("Please select a settlement"))
        
        try:
            # Decode CSV data
            csv_data = base64.b64decode(self.csv_file).decode('utf-8')
            csv_reader = csv.reader(io.StringIO(csv_data), delimiter=self.delimiter)
            
            # Skip header if present
            if self.has_header:
                next(csv_reader)
            
            # Process data
            imported_count = 0
            updated_count = 0
            errors = []
            
            # Get existing allocations if updating
            existing_allocations = {}
            if self.import_mode == 'update':
                for allocation in self.settlement_id.fee_allocation_ids:
                    existing_allocations[allocation.invoice_number] = allocation
            elif self.import_mode == 'replace':
                # Clear existing allocations
                self.settlement_id.fee_allocation_ids.unlink()
            
            # Get settlement invoices for validation
            settlement_invoices = {inv.name: inv for inv in self.settlement_id.invoice_ids}
            
            for row_num, row in enumerate(csv_reader, start=1):
                try:
                    if len(row) < max(self.invoice_column, self.base_fee_column or 0, 
                                     self.vat_input_column or 0, self.wht_column or 0):
                        errors.append(f"Row {row_num}: Not enough columns")
                        continue
                    
                    # Extract data
                    invoice_number = row[self.invoice_column - 1].strip()
                    
                    if not invoice_number:
                        continue  # Skip empty rows
                    
                    # Validate invoice exists in settlement
                    if invoice_number not in settlement_invoices:
                        errors.append(f"Row {row_num}: Invoice {invoice_number} not found in settlement")
                        continue
                    
                    # Extract amounts
                    base_fee = 0.0
                    vat_input = 0.0
                    wht = 0.0
                    
                    if self.base_fee_column and self.base_fee_column <= len(row):
                        try:
                            base_fee = float(row[self.base_fee_column - 1] or 0)
                        except ValueError:
                            errors.append(f"Row {row_num}: Invalid base fee amount")
                            continue
                    
                    if self.vat_input_column and self.vat_input_column <= len(row):
                        try:
                            vat_input = float(row[self.vat_input_column - 1] or 0)
                        except ValueError:
                            errors.append(f"Row {row_num}: Invalid VAT input amount")
                            continue
                    
                    if self.wht_column and self.wht_column <= len(row):
                        try:
                            wht = float(row[self.wht_column - 1] or 0)
                        except ValueError:
                            errors.append(f"Row {row_num}: Invalid WHT amount")
                            continue
                    
                    # Create or update allocation
                    invoice = settlement_invoices[invoice_number]
                    
                    if self.import_mode == 'update' and invoice_number in existing_allocations:
                        # Update existing allocation
                        allocation = existing_allocations[invoice_number]
                        allocation.write({
                            'base_fee_alloc': base_fee,
                            'vat_input_alloc': vat_input,
                            'wht_alloc': wht,
                            'allocation_method': 'exact',
                        })
                        # Recalculate net payout
                        allocation.net_payout_alloc = allocation.allocation_base_amount - allocation.total_deductions_alloc
                        updated_count += 1
                    else:
                        # Create new allocation
                        allocation_vals = {
                            'settlement_id': self.settlement_id.id,
                            'invoice_id': invoice.id,
                            'allocation_method': 'exact',
                            'allocation_base_amount': invoice.amount_untaxed,
                            'base_fee_alloc': base_fee,
                            'vat_input_alloc': vat_input,
                            'wht_alloc': wht,
                        }
                        
                        allocation = self.env['marketplace.fee.allocation'].create(allocation_vals)
                        # Calculate net payout
                        allocation.net_payout_alloc = allocation.allocation_base_amount - allocation.total_deductions_alloc
                        imported_count += 1
                        
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
            
            # Generate summary
            summary_lines = [
                f"Import completed:",
                f"- New allocations created: {imported_count}",
                f"- Existing allocations updated: {updated_count}",
            ]
            
            if errors:
                summary_lines.extend([
                    f"- Errors encountered: {len(errors)}",
                    "",
                    "Errors:",
                ] + errors[:10])  # Show first 10 errors
                
                if len(errors) > 10:
                    summary_lines.append(f"... and {len(errors) - 10} more errors")
            
            self.import_summary = '\n'.join(summary_lines)
            
            if imported_count + updated_count == 0:
                raise UserError(_("No valid data found to import. Please check your CSV file and column settings."))
            
            return {
                'type': 'ir.actions.act_window',
                'name': _('Import Results'),
                'res_model': 'marketplace.fee.allocation.import.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': {'show_results': True},
            }
            
        except Exception as e:
            raise UserError(_("Error processing CSV file: %s") % str(e))

    def action_view_allocations(self):
        """View the imported/updated allocations"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fee Allocations'),
            'res_model': 'marketplace.fee.allocation',
            'view_mode': 'tree,form',
            'domain': [('settlement_id', '=', self.settlement_id.id)],
            'context': {'default_settlement_id': self.settlement_id.id},
        }

    def action_download_template(self):
        """Download a CSV template for fee allocation import"""
        self.ensure_one()
        
        if not self.settlement_id or not self.settlement_id.invoice_ids:
            raise UserError(_("Please select a settlement with invoices to generate a template"))
        
        # Generate CSV template
        output = io.StringIO()
        writer = csv.writer(output, delimiter=self.delimiter)
        
        # Write header
        writer.writerow(['Invoice Number', 'Base Fee', 'VAT Input', 'WHT', 'Customer', 'Invoice Date', 'Pre-tax Amount'])
        
        # Write data rows with invoice information
        for invoice in self.settlement_id.invoice_ids:
            writer.writerow([
                invoice.name,
                '0.00',  # Base fee placeholder
                '0.00',  # VAT input placeholder
                '0.00',  # WHT placeholder
                invoice.partner_id.name,
                invoice.invoice_date.strftime('%Y-%m-%d') if invoice.invoice_date else '',
                f"{invoice.amount_untaxed:.2f}",
            ])
        
        csv_data = output.getvalue()
        output.close()
        
        # Return file download
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model=marketplace.fee.allocation.import.wizard&id={self.id}&field=template_file&filename=fee_allocation_template.csv',
            'target': 'new',
        }

    @api.model
    def get_template_csv(self, settlement_id, delimiter=','):
        """Generate template CSV content for a settlement"""
        settlement = self.env['marketplace.settlement'].browse(settlement_id)
        
        if not settlement or not settlement.invoice_ids:
            return ""
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=delimiter)
        
        # Write header
        writer.writerow(['Invoice Number', 'Base Fee', 'VAT Input', 'WHT', 'Customer', 'Invoice Date', 'Pre-tax Amount'])
        
        # Write data rows
        for invoice in settlement.invoice_ids:
            writer.writerow([
                invoice.name,
                '0.00',
                '0.00',
                '0.00',
                invoice.partner_id.name,
                invoice.invoice_date.strftime('%Y-%m-%d') if invoice.invoice_date else '',
                f"{invoice.amount_untaxed:.2f}",
            ])
        
        return output.getvalue()
