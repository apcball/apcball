from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Metadata to support advance clearing and manual linking
    expense_sheet_id = fields.Many2one('hr.expense.sheet', string='Expense Sheet', copy=False)
    advance_box_id = fields.Many2one('employee.advance.box', string='Advance Box', copy=False)
    is_expense_advance_bill = fields.Boolean(string='Is Expense Advance Bill', default=False, copy=False)
    
    # WHT Certificate support
    wht_tax_id = fields.Many2one('account.tax', string='WHT Tax', copy=False)
    wht_base_amount = fields.Monetary(string='WHT Base Amount', currency_field='currency_id', copy=False)
    wht_amount = fields.Monetary(string='WHT Amount', currency_field='currency_id', copy=False)
    is_advance_clearing = fields.Boolean(string='Is Advance Clearing Entry', default=False, copy=False)
    
    # WHT Certificate count for smart button
    wht_cert_count = fields.Integer(
        string='WHT Certificate Count',
        compute='_compute_wht_cert_count'
    )

    @api.depends('line_ids')
    def _compute_wht_cert_count(self):
        for move in self:
            count = 0
            try:
                # Check if WHT certificate module is installed
                if 'withholding.tax.cert' in self.env.registry:
                    WhtCert = self.env['withholding.tax.cert']
                    count = WhtCert.search_count([
                        ('move_id', '=', move.id)
                    ])
            except Exception:
                count = 0
            move.wht_cert_count = count

    def can_create_wht_certificate(self):
        """Check if WHT certificate can be created from this move"""
        self.ensure_one()
        return (
            self.is_advance_clearing and 
            self.wht_tax_id and 
            self.wht_amount > 0 and
            'withholding.tax.cert' in self.env.registry
        )

    def action_create_wht_certificate(self):
        """Create WHT certificate or show information"""
        self.ensure_one()
        
        # Check if WHT certificate module is available
        if 'withholding.tax.cert' not in self.env.registry:
            # Show a helpful message instead of raising an error
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WHT Certificate Module Not Available'),
                    'message': _(
                        'The Thai Withholding Tax Certificate module is not available.\n\n'
                        'You can still create WHT certificates manually through:\n'
                        '• Accounting → Vendors → Withholding Tax Certificates\n'
                        '• Or install the WHT certificate modules if available\n\n'
                        'The WHT journal entry has been created successfully with:\n'
                        '• Base Amount: %s\n'
                        '• WHT Amount: %s\n'
                        '• Tax Rate: %s%%'
                    ) % (
                        self.wht_base_amount or 0.0,
                        self.wht_amount or 0.0, 
                        abs(self.wht_tax_id.amount) if self.wht_tax_id else 0.0
                    ),
                    'type': 'info',
                    'sticky': False,
                }
            }
        
        try:
            # Open new WHT certificate form with pre-filled context
            WhtCert = self.env['withholding.tax.cert']
            
            # Find WHT move lines for reference
            wht_lines = self.line_ids.filtered(lambda l: l.tax_line_id == self.wht_tax_id)
            
            # Prepare context with default values
            context = {
                'default_company_id': self.company_id.id,
                'default_partner_id': self.partner_id.id,
                'default_date': self.date,
                'default_move_id': self.id,
                'default_state': 'draft',
            }
            
            # Add WHT information if available
            if self.wht_tax_id:
                # Calculate tax rate percentage
                tax_rate = abs(self.wht_tax_id.amount) if self.wht_tax_id else 0.0
                
                # Find corresponding account.withholding.tax record
                wht_tax_domain = [
                    ('name', 'ilike', self.wht_tax_id.name),
                    ('amount', '=', self.wht_tax_id.amount),
                ]
                
                # Try to find the withholding tax record
                withholding_tax = None
                if 'account.withholding.tax' in self.env.registry:
                    withholding_tax = self.env['account.withholding.tax'].search(wht_tax_domain, limit=1)
                
                # Prepare WHT line data for the certificate
                wht_line_vals = {
                    'base': self.wht_base_amount or 0.0,
                    'amount': self.wht_amount or 0.0,
                    'wht_percent': tax_rate,
                    'wht_cert_income_type': '2',  # Default to type 2 (fees, commission)
                    'wht_cert_income_desc': _('Advance clearing payment'),
                }
                
                # Add withholding tax if found
                if withholding_tax:
                    wht_line_vals['wht_tax_id'] = withholding_tax.id
                
                context.update({
                    # Pre-fill the WHT line
                    'default_wht_line': [(0, 0, wht_line_vals)],
                    # Additional reference information
                    'default_ref': _('Advance Clearing - %s') % (self.ref or self.name),
                    'default_origin': self.name,
                    'default_description': _('WHT from advance clearing entry: %s') % self.name,
                })
            
            return {
                'type': 'ir.actions.act_window',
                'name': _('Create WHT Certificate'),
                'res_model': 'withholding.tax.cert',
                'view_mode': 'form',
                'target': 'new',
                'context': context,
            }
            
        except Exception as e:
            _logger.warning("Failed to open WHT certificate form: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WHT Certificate Form Unavailable'),
                    'message': _(
                        'Could not open WHT certificate form: %s\n\n'
                        'You can create WHT certificates manually through the Accounting menu.\n'
                        'The advance clearing journal entry has been created successfully.'
                    ) % str(e),
                    'type': 'warning',
                    'sticky': True,
                }
            }

    def action_view_wht_certificates(self):
        """View related WHT certificates"""
        self.ensure_one()
        
        if 'withholding.tax.cert' not in self.env.registry:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WHT Certificate Module Not Available'),
                    'message': _('The WHT Certificate module is not installed. Please install the Thai localization modules.'),
                    'type': 'info',
                }
            }

        try:
            WhtCert = self.env['withholding.tax.cert']
            certificates = WhtCert.search([('move_id', '=', self.id)])

            return {
                'type': 'ir.actions.act_window',
                'name': _('WHT Certificates'),
                'res_model': 'withholding.tax.cert',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', certificates.ids)],
                'target': 'current',
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error accessing WHT certificates: %s') % str(e),
                    'type': 'warning',
                }
            }

    def action_open_wht_clear_advance_wizard_from_bill(self):
        """Open WHT Clear Advance Wizard from vendor bill"""
        self.ensure_one()
        
        if self.move_type != 'in_invoice':
            raise UserError(_("This action is only available for vendor bills."))
        
        if self.state != 'posted':
            raise UserError(_("Bill must be posted before clearing with advance."))
        
        if self.amount_residual <= 0:
            raise UserError(_("Bill has no remaining balance to clear."))
        
        # Try to find related expense sheet
        expense_sheet = self.expense_sheet_id
        if not expense_sheet:
            # Search by various methods
            ExpenseSheet = self.env['hr.expense.sheet']
            if self.invoice_origin:
                expense_sheet = ExpenseSheet.search([('name', '=', self.invoice_origin)], limit=1)
            
            if not expense_sheet and self.ref:
                # Try to parse from reference
                if 'Expense Sheet' in self.ref:
                    sheet_name = self.ref.split('Expense Sheet', 1)[1].strip().lstrip(':').strip()
                    if sheet_name:
                        expense_sheet = ExpenseSheet.search([('name', 'ilike', sheet_name)], limit=1)
        
        if not expense_sheet:
            raise UserError(_("No related expense sheet found. This bill must be created from an expense sheet to use advance clearing."))
        
        # Get advance box
        advance_box = expense_sheet.advance_box_id or self.advance_box_id
        if not advance_box:
            raise UserError(_("No advance box found. Please configure advance box for the employee."))
        
        # Get employee partner
        employee = expense_sheet.employee_id
        employee_partner = False
        if employee.user_id and employee.user_id.partner_id:
            employee_partner = employee.user_id.partner_id
        elif employee.address_home_id:
            employee_partner = employee.address_home_id
        
        context = {
            'default_expense_sheet_id': expense_sheet.id,
            'default_employee_id': employee.id,
            'default_advance_box_id': advance_box.id,
            'default_company_id': self.company_id.id,
            'default_partner_id': employee_partner.id if employee_partner else self.partner_id.id,
            'default_clear_amount': self.amount_residual,
            'default_amount_base': self.amount_residual,
        }
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Clear Advance with WHT'),
            'res_model': 'wht.clear.advance.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_advance_clearing = fields.Boolean(string='Is Advance Clearing', default=False)
    reconciled_bill_ids = fields.One2many('account.move', 'payment_id', string='Reconciled Bills')
    
    # WHT Certificate count for smart button
    wht_cert_count = fields.Integer(
        string='WHT Certificate Count',
        compute='_compute_wht_cert_count'
    )

    @api.depends('line_ids')
    def _compute_wht_cert_count(self):
        """Compute the count of WHT certificates related to this payment"""
        for payment in self:
            count = 0
            try:
                # Check if WHT certificate module is installed
                if 'l10n.th.account.wht.cert.form' in self.env.registry:
                    WhtCert = self.env['l10n.th.account.wht.cert.form']
                    count = WhtCert.search_count([
                        '|',
                        ('move_id', '=', payment.move_id.id if payment.move_id else False),
                        ('move_line_ids', 'in', payment.line_ids.ids)
                    ])
            except Exception:
                count = 0
            payment.wht_cert_count = count

    def can_create_wht_certificate(self):
        """Check if WHT certificate can be created for this payment"""
        self.ensure_one()
        return (
            self.is_advance_clearing and 
            self.move_id and
            'l10n.th.account.wht.cert.form.wizard' in self.env.registry
        )

    def action_view_wht_certificates(self):
        """View related WHT certificates for this payment"""
        self.ensure_one()
        
        try:
            if 'l10n.th.account.wht.cert.form' not in self.env.registry:
                raise UserError(_("Thai WHT Certificate module is not installed."))
            WhtCert = self.env['l10n.th.account.wht.cert.form']
        except Exception:
            return

        certificates = WhtCert.search([
            '|',
            ('move_id', '=', self.move_id.id if self.move_id else False),
            ('move_line_ids', 'in', self.line_ids.ids)
        ])

        return {
            'type': 'ir.actions.act_window',
            'name': _('WHT Certificates'),
            'res_model': 'l10n.th.account.wht.cert.form',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', certificates.ids)],
            'target': 'current',
        }