import base64
import csv
import io
from datetime import datetime
import xlrd
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ImportBankStatement(models.TransientModel):
    _name = 'import.bank.statement'
    _description = 'Import Bank Statement Wizard'

    profile_id = fields.Many2one('bank.statement.profile', string='Bank Profile', required=True)
    data_file = fields.Binary('Statement File', required=True)
    filename = fields.Char('Filename')
    
    @api.onchange('profile_id')
    def _onchange_profile_id(self):
        if self.profile_id and self.filename:
            file_extension = self.filename.split('.')[-1].lower()
            if self.profile_id.file_type == 'csv' and file_extension != 'csv':
                raise UserError(_('Please select a CSV file for this profile.'))
            elif self.profile_id.file_type == 'xlsx' and file_extension not in ['xlsx', 'xls']:
                raise UserError(_('Please select an Excel file for this profile.'))

    def _parse_csv_file(self, profile, data):
        rows = []
        try:
            csv_data = io.StringIO(data.decode(profile.encoding))
            reader = csv.reader(csv_data, delimiter=profile.delimiter)
            
            # Skip header and additional rows if configured
            for _ in range(profile.skip_rows + (1 if profile.has_header else 0)):
                next(reader, None)
                
            rows = list(reader)
        except Exception as e:
            raise UserError(_('Error parsing CSV file: %s') % str(e))
        return rows

    def _parse_excel_file(self, profile, data):
        rows = []
        try:
            wb = xlrd.open_workbook(file_contents=data)
            sheet = wb.sheet_by_index(0)
            
            # Skip header and additional rows if configured
            start_row = profile.skip_rows + (1 if profile.has_header else 0)
            
            for row_idx in range(start_row, sheet.nrows):
                row = [str(cell.value) for cell in sheet.row(row_idx)]
                rows.append(row)
        except Exception as e:
            raise UserError(_('Error parsing Excel file: %s') % str(e))
        return rows

    def _prepare_statement_line(self, profile, row):
        try:
            # Get column indices (assuming they are numbers for simplicity)
            date_idx = int(profile.date_column)
            amount_idx = int(profile.amount_column)
            description_idx = int(profile.description_column)
            reference_idx = int(profile.reference_column) if profile.reference_column else None
            partner_idx = int(profile.partner_column) if profile.partner_column else None

            # Parse date
            date_str = row[date_idx].strip()
            try:
                date = datetime.strptime(date_str, profile.date_format).date()
            except ValueError:
                raise UserError(_('Invalid date format for value: %s') % date_str)

            # Parse amount
            amount_str = row[amount_idx].strip()
            amount_str = amount_str.replace(profile.thousands_separator, '')
            amount_str = amount_str.replace(profile.decimal_separator, '.')
            try:
                amount = float(amount_str)
            except ValueError:
                raise UserError(_('Invalid amount format for value: %s') % amount_str)

            # Prepare statement line
            line_vals = {
                'date': date,
                'amount': amount,
                'payment_ref': row[description_idx].strip(),
                'ref': row[reference_idx].strip() if reference_idx is not None else False,
            }

            # Handle partner mapping if configured
            if partner_idx is not None:
                partner_ref = row[partner_idx].strip()
                if partner_ref:
                    # You might want to add logic here to map partner references to partners
                    pass

            return line_vals

        except Exception as e:
            raise UserError(_('Error preparing statement line: %s') % str(e))

    def action_import_statement(self):
        self.ensure_one()
        if not self.data_file:
            raise UserError(_('Please select a file to import.'))

        profile = self.profile_id
        data = base64.b64decode(self.data_file)
        
        # Parse file based on type
        if profile.file_type == 'csv':
            rows = self._parse_csv_file(profile, data)
        else:  # xlsx
            rows = self._parse_excel_file(profile, data)

        if not rows:
            raise UserError(_('No data found in the file to import.'))

        # Prepare statement lines
        statement_vals = {
            'name': f"{profile.bank_id.name} Statement {fields.Date.today()}",
            'journal_id': profile.journal_id.id,
            'date': fields.Date.today(),
            'line_ids': [],
        }

        for row in rows:
            line_vals = self._prepare_statement_line(profile, row)
            statement_vals['line_ids'].append((0, 0, line_vals))

        # Create bank statement
        statement = self.env['account.bank.statement'].create(statement_vals)

        return {
            'name': _('Imported Bank Statement'),
            'view_mode': 'form',
            'res_model': 'account.bank.statement',
            'res_id': statement.id,
            'type': 'ir.actions.act_window',
        }