from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class HRExpenseConfig(models.TransientModel):
    _name = 'hr.expense.config'
    _description = 'HR Expense Advance Clearing Configuration'
    _inherit = 'res.config.settings'

    vat_input_account_id = fields.Many2one(
        'account.account',
        string='VAT Input Account',
        help='Account for VAT Input (Tax Receivable)',
        domain=[('account_type', '=', 'asset_current')]
    )
    
    wht_payable_account_id = fields.Many2one(
        'account.account', 
        string='WHT Payable Account',
        help='Account for Withholding Tax Payable',
        domain=[('account_type', '=', 'liability_current')]
    )
    
    advance_account_id = fields.Many2one(
        'account.account',
        string='Employee Advance Account', 
        help='Account for Employee Advances',
        domain=[('account_type', '=', 'asset_current')]
    )

    # Store account codes as char fields for settings form
    vat_input_account_code = fields.Char(
        string='VAT Input Account Code',
        help='Account code for VAT Input (e.g., 119101)'
    )
    wht_payable_account_code = fields.Char(
        string='WHT Payable Account Code',
        help='Account code for Withholding Tax Payable (e.g., 213101)'
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        params = self.env['ir.config_parameter'].sudo()
        
        vat_account_id = params.get_param('hr_expense_advance_clearing.vat_input_account_id', False)
        wht_account_id = params.get_param('hr_expense_advance_clearing.wht_payable_account_id', False)
        advance_account_id = params.get_param('hr_expense_advance_clearing.advance_account_id', False)
        # Also load account code parameters so the form fields persist
        vat_account_code = params.get_param('hr_expense_advance_clearing.vat_input_account_code', '')
        wht_account_code = params.get_param('hr_expense_advance_clearing.wht_payable_account_code', '')
        advance_account_code = params.get_param('hr_expense_advance_clearing.advance_account_code', '')

        res.update({
            'vat_input_account_id': int(vat_account_id) if vat_account_id else False,
            'wht_payable_account_id': int(wht_account_id) if wht_account_id else False,
            'advance_account_id': int(advance_account_id) if advance_account_id else False,
            'vat_input_account_code': vat_account_code or False,
            'wht_payable_account_code': wht_account_code or False,
            'advance_account_code': advance_account_code or False,
        })
        return res

    def set_values(self):
        super().set_values()
        params = self.env['ir.config_parameter'].sudo()
        # Store IDs as strings (or empty) to avoid storing Python booleans
        if self.vat_input_account_id:
            params.set_param('hr_expense_advance_clearing.vat_input_account_id', str(self.vat_input_account_id.id))
        else:
            params.set_param('hr_expense_advance_clearing.vat_input_account_id', '')

        if self.wht_payable_account_id:
            params.set_param('hr_expense_advance_clearing.wht_payable_account_id', str(self.wht_payable_account_id.id))
        else:
            params.set_param('hr_expense_advance_clearing.wht_payable_account_id', '')

        if self.advance_account_id:
            params.set_param('hr_expense_advance_clearing.advance_account_id', str(self.advance_account_id.id))
        else:
            params.set_param('hr_expense_advance_clearing.advance_account_id', '')
        # Persist code parameters as well. If user selected an account, save its code.
        if self.vat_input_account_id:
            params.set_param('hr_expense_advance_clearing.vat_input_account_code', self.vat_input_account_id.code or '')
        else:
            params.set_param('hr_expense_advance_clearing.vat_input_account_code', self.vat_input_account_code or '')

        if self.wht_payable_account_id:
            params.set_param('hr_expense_advance_clearing.wht_payable_account_code', self.wht_payable_account_id.code or '')
        else:
            params.set_param('hr_expense_advance_clearing.wht_payable_account_code', self.wht_payable_account_code or '')

        if self.advance_account_id:
            params.set_param('hr_expense_advance_clearing.advance_account_code', self.advance_account_id.code or '')
        else:
            params.set_param('hr_expense_advance_clearing.advance_account_code', self.advance_account_code or '')
    
    advance_account_code = fields.Char(
        string='Employee Advance Account Code',
        help='Account code for Employee Advance (e.g., 141101)', 
        default='141101'
    )

    def action_save_config(self):
        """Save configuration to system parameters"""
        self.ensure_one()
        
        # Validate account codes exist
        self._validate_account_codes()
        
        # Save to system parameters
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_expense_advance_clearing.vat_input_account_code', 
            self.vat_input_account_code
        )
        
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_expense_advance_clearing.wht_payable_account_code',
            self.wht_payable_account_code
        )
        
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_expense_advance_clearing.advance_account_code',
            self.advance_account_code
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Configuration saved successfully!'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _validate_account_codes(self):
        """Validate that account codes exist in chart of accounts"""
        company_id = self.env.company.id
        
        # Check VAT Input account
        if self.vat_input_account_code:
            vat_account = self.env['account.account'].search([
                ('code', '=', self.vat_input_account_code),
                ('company_id', '=', company_id)
            ])
            if not vat_account:
                raise ValidationError(
                    _('VAT Input account with code "%s" not found in chart of accounts.') 
                    % self.vat_input_account_code
                )
        
        # Check WHT Payable account
        if self.wht_payable_account_code:
            wht_account = self.env['account.account'].search([
                ('code', '=', self.wht_payable_account_code),
                ('company_id', '=', company_id)
            ])
            if not wht_account:
                raise ValidationError(
                    _('WHT Payable account with code "%s" not found in chart of accounts.') 
                    % self.wht_payable_account_code
                )
        
        # Check Advance account
        if self.advance_account_code:
            advance_account = self.env['account.account'].search([
                ('code', '=', self.advance_account_code),
                ('company_id', '=', company_id)
            ])
            if not advance_account:
                raise ValidationError(
                    _('Employee Advance account with code "%s" not found in chart of accounts.') 
                    % self.advance_account_code
                )

    @api.model
    def default_get(self, fields_list):
        """Load current configuration from system parameters"""
        defaults = super().default_get(fields_list)
        
        # Load current values from system parameters
        defaults['vat_input_account_code'] = self.env['ir.config_parameter'].sudo().get_param(
            'hr_expense_advance_clearing.vat_input_account_code', '119101'
        )
        
        defaults['wht_payable_account_code'] = self.env['ir.config_parameter'].sudo().get_param(
            'hr_expense_advance_clearing.wht_payable_account_code', '213101'
        )
        
        defaults['advance_account_code'] = self.env['ir.config_parameter'].sudo().get_param(
            'hr_expense_advance_clearing.advance_account_code', '141101'
        )
        
        return defaults

    def action_create_missing_accounts(self):
        """Create missing accounts if they don't exist"""
        self.ensure_one()
        company_id = self.env.company.id
        created_accounts = []
        
        # Create VAT Input account if missing
        if self.vat_input_account_code:
            vat_account = self.env['account.account'].search([
                ('code', '=', self.vat_input_account_code),
                ('company_id', '=', company_id)
            ])
            if not vat_account:
                vat_account = self.env['account.account'].create({
                    'code': self.vat_input_account_code,
                    'name': 'VAT Input Tax',
                    'account_type': 'asset_current',
                    'company_id': company_id,
                })
                created_accounts.append(vat_account.display_name)
        
        # Create WHT Payable account if missing
        if self.wht_payable_account_code:
            wht_account = self.env['account.account'].search([
                ('code', '=', self.wht_payable_account_code),
                ('company_id', '=', company_id)
            ])
            if not wht_account:
                wht_account = self.env['account.account'].create({
                    'code': self.wht_payable_account_code,
                    'name': 'Withholding Tax Payable',
                    'account_type': 'liability_current',
                    'company_id': company_id,
                })
                created_accounts.append(wht_account.display_name)
        
        # Create Advance account if missing
        if self.advance_account_code:
            advance_account = self.env['account.account'].search([
                ('code', '=', self.advance_account_code),
                ('company_id', '=', company_id)
            ])
            if not advance_account:
                advance_account = self.env['account.account'].create({
                    'code': self.advance_account_code,
                    'name': 'Employee Advance',
                    'account_type': 'asset_current',
                    'company_id': company_id,
                })
                created_accounts.append(advance_account.display_name)
        
        if created_accounts:
            message = _('Created accounts: %s') % ', '.join(created_accounts)
        else:
            message = _('All accounts already exist.')
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Account Creation'),
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def create(self, vals):
        # Ensure set_values runs so params persist when settings are saved
        rec = super().create(vals)
        try:
            rec.set_values()
        except Exception as e:
            _logger.exception('Failed to persist settings on create: %s', e)
        return rec

    def write(self, vals):
        res = super().write(vals)
        try:
            # ensure the current record's values are persisted
            self.set_values()
        except Exception as e:
            _logger.exception('Failed to persist settings on write: %s', e)
        return res