# Copyright 2024 Ecosoft Co., Ltd (http://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class WhtSetupWizard(models.TransientModel):
    _name = 'wht.setup.wizard'
    _description = 'Withholding Tax Setup Wizard'

    state = fields.Selection([
        ('step1', 'Step 1: Account Setup'),
        ('step2', 'Step 2: Tax Types'),
        ('step3', 'Step 3: Verification'),
        ('complete', 'Setup Complete')
    ], default='step1', string='Setup Step')

    # Step 1: Account Setup
    wht_account_id = fields.Many2one(
        'account.account',
        string='WHT Payable Account',
        help='Account for withholding tax payable'
    )
    create_wht_account = fields.Boolean(
        string='Create New WHT Account',
        default=True,
        help='Create a new account for withholding tax'
    )
    wht_account_code = fields.Char(
        string='Account Code',
        default='2131',
        help='Code for the new WHT account'
    )
    wht_account_name = fields.Char(
        string='Account Name',
        default='Withholding Tax Payable',
        help='Name for the new WHT account'
    )

    # Step 2: Tax Types
    create_service_wht = fields.Boolean(
        string='Create Service WHT 3%',
        default=True,
        help='Create withholding tax for services (3%)'
    )
    create_rent_wht = fields.Boolean(
        string='Create Rental WHT 5%',
        default=True,
        help='Create withholding tax for rental income (5%)'
    )
    create_pit = fields.Boolean(
        string='Create Personal Income Tax',
        default=True,
        help='Create personal income tax withholding'
    )

    # Step 3: Verification
    verification_results = fields.Text(
        string='Verification Results',
        readonly=True
    )

    def action_next_step(self):
        """Move to next setup step"""
        if self.state == 'step1':
            self._setup_accounts()
            self.state = 'step2'
        elif self.state == 'step2':
            self._setup_tax_types()
            self.state = 'step3'
            self._run_verification()
        elif self.state == 'step3':
            self.state = 'complete'
            return self._show_completion_message()
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wht.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_previous_step(self):
        """Move to previous setup step"""
        if self.state == 'step2':
            self.state = 'step1'
        elif self.state == 'step3':
            self.state = 'step2'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wht.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _setup_accounts(self):
        """Setup WHT accounts"""
        if self.create_wht_account:
            # Check if account with same code exists
            existing_account = self.env['account.account'].search([
                ('code', '=', self.wht_account_code)
            ])
            
            if existing_account:
                if not existing_account.wht_account:
                    existing_account.wht_account = True
                self.wht_account_id = existing_account
            else:
                # Create new account
                self.wht_account_id = self.env['account.account'].create({
                    'name': self.wht_account_name,
                    'code': self.wht_account_code,
                    'account_type': 'liability_current',
                    'wht_account': True,
                })
        else:
            # Mark existing account as WHT account
            if self.wht_account_id:
                self.wht_account_id.wht_account = True

    def _setup_tax_types(self):
        """Setup WHT tax types"""
        if not self.wht_account_id:
            raise UserError(_('WHT account must be configured first'))

        tax_types = []

        if self.create_service_wht:
            tax_types.append({
                'name': 'Service WHT 3%',
                'amount': 3.0,
                'income_tax_form': 'pnd3',
                'wht_cert_income_type': '2',
            })

        if self.create_rent_wht:
            tax_types.append({
                'name': 'Rental WHT 5%',
                'amount': 5.0,
                'income_tax_form': 'pnd3',
                'wht_cert_income_type': '3',
            })

        if self.create_pit:
            tax_types.append({
                'name': 'Personal Income Tax',
                'amount': 0.0,
                'is_pit': True,
                'income_tax_form': 'pnd1',
                'wht_cert_income_type': '1',
            })

        for tax_data in tax_types:
            # Check if tax already exists
            existing_tax = self.env['account.withholding.tax'].search([
                ('name', '=', tax_data['name'])
            ])
            
            if not existing_tax:
                tax_data['account_id'] = self.wht_account_id.id
                self.env['account.withholding.tax'].create(tax_data)

    def _run_verification(self):
        """Run verification checks"""
        results = []
        
        # Check WHT accounts
        wht_accounts = self.env['account.account'].search([('wht_account', '=', True)])
        if wht_accounts:
            results.append(f"✓ {len(wht_accounts)} WHT account(s) configured")
        else:
            results.append("✗ No WHT accounts found")

        # Check WHT tax types
        wht_taxes = self.env['account.withholding.tax'].search([])
        if wht_taxes:
            results.append(f"✓ {len(wht_taxes)} WHT tax type(s) configured")
            for tax in wht_taxes:
                if tax.account_id:
                    results.append(f"  ✓ {tax.name} - Account: {tax.account_id.code}")
                else:
                    results.append(f"  ✗ {tax.name} - No account set")
        else:
            results.append("✗ No WHT tax types found")

        # Check PIT rates if PIT was created
        if self.create_pit:
            pit_rates = self.env['personal.income.tax'].search([])
            if pit_rates:
                results.append(f"✓ {len(pit_rates)} PIT rate(s) configured")
            else:
                results.append("⚠ No PIT rates configured - will use default")

        # Check user permissions
        if self.env.user.has_group('account.group_account_user'):
            results.append("✓ User has accounting access")
        else:
            results.append("✗ User lacks accounting access")

        self.verification_results = '\n'.join(results)

    def _show_completion_message(self):
        """Show setup completion message"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('WHT Setup Complete'),
            'res_model': 'wht.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'setup_complete': True
            }
        }

    def action_open_wht_config(self):
        """Open WHT configuration menu"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Withholding Tax'),
            'res_model': 'account.withholding.tax',
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def action_open_accounts(self):
        """Open chart of accounts"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Chart of Accounts'),
            'res_model': 'account.account',
            'view_mode': 'tree,form',
            'domain': [('wht_account', '=', True)],
            'target': 'current',
        }
