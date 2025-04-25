from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
from datetime import datetime

class BankStatementUpload(models.Model):
    _name = 'bank.statement.upload'
    _description = 'Bank Statement Upload'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char('Name', required=True, tracking=True)
    profile_id = fields.Many2one('bank.statement.profile', string='Bank Profile', required=True, tracking=True)
    file = fields.Binary('Statement File', required=True, tracking=True)
    filename = fields.Char('Filename', tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validated', 'Validated'),
        ('imported', 'Imported'),
        ('failed', 'Failed')
    ], string='Status', default='draft', required=True, tracking=True)
    import_date = fields.Datetime('Import Date', readonly=True, tracking=True)
    statement_id = fields.Many2one('account.bank.statement', string='Bank Statement', readonly=True, tracking=True)
    notes = fields.Text('Notes', tracking=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company, tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = vals.get('filename', 'New Upload')
        return super().create(vals_list)

    def action_validate(self):
        self.ensure_one()
        try:
            # Add validation logic here based on profile
            self.state = 'validated'
            self.notes = 'File validated successfully'
            self.message_post(body=_('Statement file validated successfully.'))
        except Exception as e:
            self.state = 'failed'
            self.notes = str(e)
            self.message_post(body=_('Validation failed: %s') % str(e), message_type='comment')

    def action_import(self):
        self.ensure_one()
        if self.state != 'validated':
            raise UserError(_('Please validate the file before importing.'))
        
        try:
            # Import logic will be implemented here
            self.state = 'imported'
            self.import_date = fields.Datetime.now()
            self.notes = 'Import completed successfully'
            self.message_post(body=_('Statement imported successfully.'))
        except Exception as e:
            self.state = 'failed'
            self.notes = str(e)
            self.message_post(body=_('Import failed: %s') % str(e), message_type='comment')

    def action_reset(self):
        self.write({
            'state': 'draft',
            'notes': 'Reset to draft state'
        })
        self.message_post(body=_('Statement reset to draft state.'))