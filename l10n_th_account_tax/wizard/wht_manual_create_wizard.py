# Copyright 2019 Ecosoft Co., Ltd (http://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WhtManualCreateWizard(models.TransientModel):
    _name = 'wht.manual.create.wizard'
    _description = 'Manual WHT Certificate Creation Wizard'

    payment_id = fields.Many2one(
        'account.payment',
        string='Payment'
    )
    move_id = fields.Many2one(
        'account.move',
        string='Invoice/Bill'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True
    )
    amount_total = fields.Monetary(
        string='Payment Amount',
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    wht_tax_amount = fields.Monetary(
        string='WHT Tax Amount',
        currency_field='currency_id',
        required=True
    )
    wht_base_amount = fields.Monetary(
        string='WHT Base Amount',
        currency_field='currency_id',
        required=True
    )
    wht_tax_rate = fields.Float(
        string='WHT Tax Rate (%)',
        default=3.0
    )
    income_tax_form = fields.Selection([
        ('pnd1', 'PND1'),
        ('pnd3', 'PND3'),
        ('pnd53', 'PND53'),
    ], string='Income Tax Form', default='pnd3', required=True)
    wht_cert_income_type = fields.Selection([
        ('1', '1. เงินเดือน ค่าจ้าง ฯลฯ 40(1)'),
        ('2', '2. ค่าธรรมเนียม ค่านายหน้า ฯลฯ 40(2)'),
        ('3', '3. ค่าแห่งลิขสิทธิ์ ฯลฯ 40(3)'),
        ('5', '5. ค่าจ้างทำของ ค่าบริการ'),
        ('6', '6. อื่นๆ'),
    ], string='Income Type', default='5', required=True)

    @api.model
    def default_get(self, fields_list):
        """Set default values from context"""
        res = super().default_get(fields_list)
        
        # Get values from context
        if self.env.context.get('default_move_id'):
            res['move_id'] = self.env.context.get('default_move_id')
        if self.env.context.get('default_payment_id'):
            res['payment_id'] = self.env.context.get('default_payment_id')
        if self.env.context.get('default_partner_id'):
            res['partner_id'] = self.env.context.get('default_partner_id')
        if self.env.context.get('default_wht_base_amount'):
            res['wht_base_amount'] = self.env.context.get('default_wht_base_amount')
        if self.env.context.get('default_wht_tax_amount'):
            res['wht_tax_amount'] = self.env.context.get('default_wht_tax_amount')
            
        # Calculate rate if both base and tax are available
        if res.get('wht_base_amount') and res.get('wht_tax_amount'):
            rate = (res['wht_tax_amount'] / res['wht_base_amount']) * 100
            res['wht_tax_rate'] = rate
        
        return res

    @api.onchange('wht_tax_amount', 'wht_tax_rate')
    def _onchange_wht_calculate_base(self):
        if self.wht_tax_amount and self.wht_tax_rate:
            self.wht_base_amount = (self.wht_tax_amount * 100) / self.wht_tax_rate

    @api.onchange('wht_base_amount', 'wht_tax_rate')
    def _onchange_base_calculate_tax(self):
        if self.wht_base_amount and self.wht_tax_rate:
            self.wht_tax_amount = (self.wht_base_amount * self.wht_tax_rate) / 100

    def action_create_wht_cert(self):
        """Create WHT certificate manually"""
        self.ensure_one()
        
        # Validation 1: Check required fields
        if not self.wht_tax_amount or not self.wht_base_amount:
            raise UserError(_('Please specify both WHT tax amount and base amount.'))
        
        # Validation 2: Check if certificate already exists
        existing_certs = False
        if self.move_id:
            existing_certs = self.env['withholding.tax.cert'].search([
                ('move_id', '=', self.move_id.id)
            ])
        elif self.payment_id:
            existing_certs = self.env['withholding.tax.cert'].search([
                ('payment_id', '=', self.payment_id.id)
            ])
        
        if existing_certs:
            raise UserError(_('WHT Certificate already exists for this document. Please check existing certificates.'))
        
        # Validation 3: Check reasonable amounts
        if self.wht_tax_amount <= 0:
            raise UserError(_('WHT tax amount must be greater than 0.'))
        
        if self.wht_base_amount <= 0:
            raise UserError(_('WHT base amount must be greater than 0.'))
        
        # Validation 4: Check if rate is reasonable (between 0.1% and 20%)
        calculated_rate = (self.wht_tax_amount / self.wht_base_amount) * 100
        if calculated_rate < 0.1 or calculated_rate > 20:
            raise UserError(_('WHT rate (%.2f%%) seems unreasonable. Please check your amounts.') % calculated_rate)
        
        # Create WHT certificate
        cert_vals = {
            'partner_id': self.partner_id.id,
            'date': fields.Date.today(),
            'state': 'draft',
            'company_partner_id': self.env.company.partner_id.id,
            'company_id': self.env.company.id,
            'currency_id': self.currency_id.id,
            'income_tax_form': self.income_tax_form,
        }
        
        # Link to payment or move
        if self.payment_id:
            cert_vals['payment_id'] = self.payment_id.id
            cert_vals['date'] = self.payment_id.date
        elif self.move_id:
            cert_vals['move_id'] = self.move_id.id
            cert_vals['date'] = self.move_id.date
        
        cert = self.env['withholding.tax.cert'].create(cert_vals)
        
        # Create certificate line
        line_vals = {
            'cert_id': cert.id,
            'base': self.wht_base_amount,
            'amount': self.wht_tax_amount,
            'wht_cert_income_type': self.wht_cert_income_type,
        }
        
        self.env['withholding.tax.cert.line'].create(line_vals)
        
        # Success message
        document_ref = self.move_id.name if self.move_id else self.payment_id.name
        message = f'WHT Certificate created successfully for {document_ref}'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }
