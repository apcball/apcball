from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import base64
import csv
import io
import re
from datetime import datetime


class MarketplaceDocumentImportWizard(models.TransientModel):
    _name = 'marketplace.document.import.wizard'
    _description = 'Marketplace Document Import Wizard'

    document_type = fields.Selection([
        ('shopee_tr', 'Shopee Tax Invoice (TR)'),
        ('spx_rc', 'SPX Receipt (RC)')
    ], string='Document Type', required=True)
    
    import_method = fields.Selection([
        ('manual', 'Manual Entry'),
        ('csv', 'CSV Import')
    ], string='Import Method', default='manual', required=True)
    
    # Manual entry fields
    document_reference = fields.Char('Document Reference')
    partner_id = fields.Many2one('res.partner', string='Vendor')
    profile_id = fields.Many2one('marketplace.settlement.profile', string='Trade Channel Profile')
    date = fields.Date('Date', default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', string='Bill Journal',
                               domain="[('type', '=', 'purchase')]")
    
    # CSV import fields
    csv_file = fields.Binary('CSV File')
    csv_filename = fields.Char('Filename')
    csv_delimiter = fields.Selection([
        (',', 'Comma (,)'),
        (';', 'Semicolon (;)'),
        ('\t', 'Tab'),
        ('|', 'Pipe (|)')
    ], string='CSV Delimiter', default=',')
    
    # Preview data
    preview_data = fields.Text('Preview Data', readonly=True)
    
    notes = fields.Text('Notes')

    @api.onchange('document_type')
    def _onchange_document_type(self):
        """Set default profile and partner based on document type"""
        if self.document_type == 'shopee_tr':
            profile = self.env['marketplace.settlement.profile'].get_profile_by_channel('shopee')
            if profile:
                self.profile_id = profile.id
                self._apply_profile_defaults()
        elif self.document_type == 'spx_rc':
            profile = self.env['marketplace.settlement.profile'].get_profile_by_channel('spx')
            if profile:
                self.profile_id = profile.id
                self._apply_profile_defaults()

    @api.onchange('profile_id')
    def _onchange_profile_id(self):
        """Apply profile defaults"""
        if self.profile_id:
            self._apply_profile_defaults()

    def _apply_profile_defaults(self):
        """Apply defaults from selected profile"""
        if not self.profile_id:
            return
            
        profile = self.profile_id
        if profile.vendor_partner_id:
            self.partner_id = profile.vendor_partner_id
        if profile.purchase_journal_id:
            self.journal_id = profile.purchase_journal_id

    @api.onchange('csv_file', 'csv_delimiter')
    def _onchange_csv_file(self):
        """Preview CSV file content"""
        if self.csv_file:
            try:
                csv_data = base64.b64decode(self.csv_file).decode('utf-8')
                csv_reader = csv.reader(io.StringIO(csv_data), delimiter=self.csv_delimiter)
                preview_lines = []
                for i, row in enumerate(csv_reader):
                    if i >= 10:  # Show first 10 lines
                        break
                    preview_lines.append(' | '.join(row))
                self.preview_data = '\n'.join(preview_lines)
            except Exception as e:
                self.preview_data = f'Error reading CSV: {str(e)}'

    def action_import_manual(self):
        """Create vendor bill from manual entry"""
        if self.import_method != 'manual':
            raise UserError(_('This action is only for manual import'))
        
        self._validate_manual_fields()
        
        # Create vendor bill document
        vendor_bill = self.env['marketplace.vendor.bill'].create({
            'document_reference': self.document_reference,
            'document_type': self.document_type,
            'partner_id': self.partner_id.id,
            'profile_id': self.profile_id.id if self.profile_id else False,
            'date': self.date,
            'journal_id': self.journal_id.id,
            'notes': self.notes,
        })
        
        # Add default lines based on profile (will be handled by the model's onchange)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Marketplace Vendor Bill'),
            'res_model': 'marketplace.vendor.bill',
            'res_id': vendor_bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_import_csv(self):
        """Import vendor bills from CSV file"""
        if self.import_method != 'csv':
            raise UserError(_('This action is only for CSV import'))
        
        if not self.csv_file:
            raise UserError(_('Please upload a CSV file'))
        
        created_bills = self._process_csv_import()
        
        # Return action to view created bills
        return {
            'type': 'ir.actions.act_window',
            'name': _('Imported Vendor Bills'),
            'res_model': 'marketplace.vendor.bill',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created_bills.ids)],
            'target': 'current',
        }

    def _validate_manual_fields(self):
        """Validate manual entry fields"""
        if not self.document_reference:
            raise UserError(_('Document reference is required'))
        if not self.partner_id:
            raise UserError(_('Vendor is required'))
        if not self.journal_id:
            raise UserError(_('Bill journal is required'))
        
        # Validate document reference format
        if self.document_type == 'shopee_tr':
            if not re.match(r'^TR[A-Z0-9]+$', self.document_reference):
                raise UserError(_('Shopee Tax Invoice reference must start with "TR"'))
        elif self.document_type == 'spx_rc':
            if not re.match(r'^RC[A-Z0-9]+$', self.document_reference):
                raise UserError(_('SPX Receipt reference must start with "RC"'))
        
        # Check for duplicates
        existing = self.env['marketplace.vendor.bill'].search([
            ('document_reference', '=', self.document_reference),
            ('document_type', '=', self.document_type)
        ])
        if existing:
            raise UserError(_('Document reference %s already exists') % self.document_reference)

    def _add_default_lines(self, vendor_bill):
        """Add default lines based on document type"""
        if self.document_type == 'shopee_tr':
            # Default Shopee lines
            lines_data = [
                {
                    'description': 'Platform Commission',
                    'account_id': self._get_default_account('commission').id,
                    'amount': 0.0,
                    'vat_rate': 7.0,
                    'wht_rate': 3.0,
                    'sequence': 10
                },
                {
                    'description': 'Service Fees',
                    'account_id': self._get_default_account('service').id,
                    'amount': 0.0,
                    'vat_rate': 7.0,
                    'wht_rate': 3.0,
                    'sequence': 20
                },
                {
                    'description': 'Advertising Fees',
                    'account_id': self._get_default_account('advertising').id,
                    'amount': 0.0,
                    'vat_rate': 7.0,
                    'wht_rate': 3.0,
                    'sequence': 30
                }
            ]
        else:  # spx_rc
            # Default SPX lines
            lines_data = [
                {
                    'description': 'Logistics Fees',
                    'account_id': self._get_default_account('logistics').id,
                    'amount': 0.0,
                    'vat_rate': 0.0,
                    'wht_rate': 1.0,
                    'sequence': 10
                },
                {
                    'description': 'Shipping Charges',
                    'account_id': self._get_default_account('shipping').id,
                    'amount': 0.0,
                    'vat_rate': 0.0,
                    'wht_rate': 1.0,
                    'sequence': 20
                }
            ]
        
        # Create lines
        for line_data in lines_data:
            line_data['bill_id'] = vendor_bill.id
            self.env['marketplace.vendor.bill.line'].create(line_data)

    def _get_default_account(self, account_type):
        """Get default expense account by type"""
        account_mapping = {
            'commission': '6201',  # Marketplace Commission
            'service': '6202',     # Service Fees
            'advertising': '6203', # Advertising Expense
            'logistics': '6204',   # Logistics Expense
            'shipping': '6205',    # Shipping Expense
        }
        
        account_code = account_mapping.get(account_type)
        if account_code:
            account = self.env['account.account'].search([('code', '=', account_code)], limit=1)
            if account:
                return account
        
        # Fallback to first expense account
        return self.env['account.account'].search([
            ('account_type', 'in', ['expense', 'asset_expense'])
        ], limit=1)

    def _process_csv_import(self):
        """Process CSV file and create vendor bills"""
        csv_data = base64.b64decode(self.csv_file).decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_data), delimiter=self.csv_delimiter)
        
        created_bills = self.env['marketplace.vendor.bill']
        errors = []
        
        for row_num, row in enumerate(csv_reader, start=2):
            try:
                bill = self._create_bill_from_csv_row(row)
                created_bills |= bill
            except Exception as e:
                errors.append(f'Row {row_num}: {str(e)}')
        
        if errors:
            error_msg = '\n'.join(errors[:10])  # Show first 10 errors
            if len(errors) > 10:
                error_msg += f'\n... and {len(errors) - 10} more errors'
            raise UserError(_('Import completed with errors:\n%s') % error_msg)
        
        return created_bills

    def _create_bill_from_csv_row(self, row):
        """Create vendor bill from CSV row"""
        # Expected CSV columns:
        # document_reference, date, partner_name, description, amount, vat_rate, wht_rate, account_code
        
        document_reference = row.get('document_reference', '').strip()
        if not document_reference:
            raise ValidationError(_('Document reference is required'))
        
        # Parse date
        date_str = row.get('date', '').strip()
        try:
            bill_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            try:
                bill_date = datetime.strptime(date_str, '%d/%m/%Y').date()
            except ValueError:
                bill_date = fields.Date.context_today(self)
        
        # Find or create partner
        partner_name = row.get('partner_name', '').strip()
        if partner_name:
            partner = self.env['res.partner'].search([('name', 'ilike', partner_name)], limit=1)
            if not partner:
                partner = self.env['res.partner'].create({'name': partner_name, 'is_company': True})
        else:
            partner = self.partner_id
        
        # Create or find existing vendor bill
        existing_bill = self.env['marketplace.vendor.bill'].search([
            ('document_reference', '=', document_reference),
            ('document_type', '=', self.document_type)
        ])
        
        if existing_bill:
            vendor_bill = existing_bill
        else:
            vendor_bill = self.env['marketplace.vendor.bill'].create({
                'document_reference': document_reference,
                'document_type': self.document_type,
                'partner_id': partner.id,
                'date': bill_date,
                'journal_id': self.journal_id.id,
                'notes': self.notes,
            })
        
        # Add line
        description = row.get('description', '').strip()
        amount = float(row.get('amount', 0))
        vat_rate = float(row.get('vat_rate', 0))
        wht_rate = float(row.get('wht_rate', 0))
        account_code = row.get('account_code', '').strip()
        
        # Find account
        if account_code:
            account = self.env['account.account'].search([('code', '=', account_code)], limit=1)
        if not account_code or not account:
            account = self._get_default_account('commission')
        
        self.env['marketplace.vendor.bill.line'].create({
            'bill_id': vendor_bill.id,
            'description': description or 'Imported line',
            'account_id': account.id,
            'amount': amount,
            'vat_rate': vat_rate,
            'wht_rate': wht_rate,
        })
        
        return vendor_bill

    def action_download_template(self):
        """Download CSV template"""
        template_data = [
            ['document_reference', 'date', 'partner_name', 'description', 'amount', 'vat_rate', 'wht_rate', 'account_code'],
            ['TR123456789', '2024-01-15', 'Shopee Thailand', 'Platform Commission', '1000.00', '7.0', '3.0', '6201'],
            ['TR123456789', '2024-01-15', 'Shopee Thailand', 'Service Fees', '500.00', '7.0', '3.0', '6202'],
            ['RC987654321', '2024-01-15', 'SPX Technologies', 'Logistics Fees', '300.00', '0.0', '1.0', '6204'],
        ]
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=self.csv_delimiter)
        for row in template_data:
            writer.writerow(row)
        
        csv_content = output.getvalue().encode('utf-8')
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'data:text/csv;charset=utf-8;base64,{base64.b64encode(csv_content).decode()}',
            'target': 'self',
            'download': True,
        }
