from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64

class ImportBankStatement(models.TransientModel):
    _name = 'import.bank.statement'
    _description = 'Import Bank Statement'

    profile_id = fields.Many2one('bank.statement.profile', string='Import Profile', required=True)
    data_file = fields.Binary(string='Bank Statement File', required=True)
    filename = fields.Char('Filename')

    def action_import_statement(self):
        self.ensure_one()
        if not self.data_file:
            raise UserError(_('Please select a file to import.'))

        file_data = base64.b64decode(self.data_file)
        statement = self.profile_id.import_statement_file(file_data, self.filename)
        
        if statement:
            # Show the imported bank statement
            action = {
                'name': _('Imported Bank Statement'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.bank.statement',
                'res_id': statement.id,
                'view_mode': 'form',
                'view_type': 'form',
                'target': 'current',
            }
            return action
        else:
            raise UserError(_('No transactions were imported. Please check your file and import settings.'))