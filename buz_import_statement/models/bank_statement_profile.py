from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class BankStatementProfile(models.Model):
    _name = 'bank.statement.profile'
    _description = 'Bank Statement Import Profile'

    name = fields.Char('Profile Name', required=True)
    bank_id = fields.Many2one('res.bank', string='Bank', required=True)
    journal_id = fields.Many2one('account.journal', string='Bank Journal', required=True,
                                domain=[('type', '=', 'bank')])
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                 default=lambda self: self.env.company.currency_id)
    
    # File configuration
    file_encoding = fields.Char('File Encoding', default='utf-8', required=True)
    date_format = fields.Char('Date Format', default='%d/%m/%Y', required=True)
    decimal_separator = fields.Char('Decimal Separator', default='.', required=True)
    thousands_separator = fields.Char('Thousands Separator', default=',', required=True)
    skip_rows = fields.Integer('Skip Rows', default=9, help='Number of rows to skip at the beginning')
    active = fields.Boolean(default=True)

    def import_file(self, data_file):
        self.ensure_one()
        if not data_file:
            raise UserError(_('Please select a file to import.'))
        
        try:
            # Decode file content
            data = data_file.decode(self.file_encoding)
        except UnicodeDecodeError as e:
            raise UserError(_('Unable to decode file: %s') % str(e))

        # Split lines and remove empty ones
        lines = [line for line in data.split('\n') if line.strip()]
        
        # Skip header rows
        if len(lines) <= self.skip_rows:
            raise UserError(_('File contains too few lines after skipping headers.'))
        
        data_lines = lines[self.skip_rows:]
        transactions = []
        
        # Process each line
        for line in data_lines:
            # Skip empty lines and footer
            if not line.strip() or line.strip().startswith('**'):
                continue
            
            # Split CSV line
            row = line.split(',')
            if len(row) < 12:  # Ensure minimum columns exist
                continue
            
            try:
                # Parse date (column 0)
                date_str = row[0].strip()
                if not date_str:
                    continue
                
                try:
                    # Convert Thai date to Gregorian
                    day, month, year = date_str.split('/')
                    year = int(year) - 543  # Convert BE to CE
                    date = datetime.strptime(f"{day.zfill(2)}/{month.zfill(2)}/{year}", "%d/%m/%Y").date()
                except (ValueError, IndexError) as e:
                    _logger.error(f"Date parsing error for {date_str}: {str(e)}")
                    continue
                
                # Parse amounts (columns 4 and 5)
                try:
                    # Process debit amount (column 4)
                    debit_str = row[4].strip()
                    debit = 0.0
                    if debit_str:
                        debit_str = debit_str.replace(self.thousands_separator, '')
                        debit = float(debit_str)
                    
                    # Process credit amount (column 5)
                    credit_str = row[5].strip()
                    credit = 0.0
                    if credit_str:
                        credit_str = credit_str.replace(self.thousands_separator, '')
                        credit = float(credit_str)
                    
                    amount = credit - debit
                except (ValueError, IndexError) as e:
                    _logger.error(f"Amount parsing error: {str(e)}")
                    continue
                
                if amount == 0:
                    continue
                
                # Build description
                desc_parts = []
                transaction_type = row[2].strip()  # Column 2: Transaction type
                ref_number = row[7].strip()        # Column 7: Reference number
                channel = row[10].strip()          # Column 10: Channel
                details = row[11].strip()          # Column 11: Details
                
                if transaction_type:
                    desc_parts.append(transaction_type)
                if ref_number:
                    desc_parts.append(f"Ref: {ref_number}")
                if channel:
                    desc_parts.append(f"ช่องทาง: {channel}")
                if details:
                    desc_parts.append(details)
                
                description = ' - '.join(filter(None, desc_parts))
                
                # Create transaction dict
                transaction = {
                    'date': date,
                    'amount': amount,
                    'description': description,
                    'ref': ref_number or '',
                }
                transactions.append(transaction)
                
            except Exception as e:
                _logger.error(f"Error processing line: {str(e)}")
                continue
        
        if not transactions:
            raise UserError(_('No transactions found in file.'))
        
        # Create bank statement
        statement_vals = {
            'name': f"Bank Statement {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            'date': transactions[0]['date'],  # Use first transaction date
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id.id,
            'line_ids': [(0, 0, t) for t in transactions],
        }
        
        statement = self.env['account.bank.statement'].create(statement_vals)
        return statement