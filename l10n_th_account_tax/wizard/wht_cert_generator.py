# Copyright 2024 Ecosoft Co., Ltd (https://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class WhtCertGenerator(models.TransientModel):
    _name = 'wht.cert.generator'
    _description = 'WHT Certificate Generator Wizard'
    
    payment_id = fields.Many2one(
        'account.payment',
        string='Payment',
        required=True,
        readonly=True,
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        related='payment_id.partner_id',
        readonly=True,
    )
    
    income_tax_form = fields.Selection(
        [
            ("pnd1", "PND1"),
            ("pnd2", "PND2"), 
            ("pnd3", "PND3"),
            ("pnd3a", "PND3a"),
            ("pnd53", "PND53"),
        ],
        string='Income Tax Form',
        default='pnd3',
        required=True,
    )
    
    wht_cert_line_ids = fields.One2many(
        'wht.cert.generator.line',
        'wizard_id',
        string='WHT Certificate Lines',
    )
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        payment_id = self.env.context.get('active_id')
        
        if payment_id:
            payment = self.env['account.payment'].browse(payment_id)
            res['payment_id'] = payment_id
            
            # Get WHT data from payment
            wht_data = payment._get_wht_tax_data()
            
            # Create wizard lines
            lines = []
            for data in wht_data:
                line_vals = {
                    'partner_id': data['partner_id'],
                    'base_amount': data['base_amount'],
                    'wht_amount': data['wht_amount'],
                    'wht_cert_income_type': self._map_income_type_to_cert_type(data.get('income_type', 'other')),
                    'tax_id': data.get('tax_id'),
                }
                lines.append((0, 0, line_vals))
            
            res['wht_cert_line_ids'] = lines
            
        return res
    
    def _map_income_type_to_cert_type(self, income_type):
        """Map income type to WHT certificate income type"""
        mapping = {
            'service': '5',      # ค่าจ้างทำของ ค่าบริการ ค่าเช่า ค่าขนส่ง ฯลฯ 3 เตรส
            'rental': '5',       # ค่าจ้างทำของ ค่าบริการ ค่าเช่า ค่าขนส่ง ฯลฯ 3 เตรส
            'professional': '2', # ค่าธรรมเนียม ค่านายหน้า ฯลฯ 40(2)
            'transport': '5',    # ค่าจ้างทำของ ค่าบริการ ค่าเช่า ค่าขนส่ง ฯลฯ 3 เตรส
            'other': '6',        # อื่นๆ (ระบุ)
        }
        return mapping.get(income_type, '6')
    
    def action_generate_wht_cert(self):
        """Generate WHT certificate with wizard data"""
        if not self.wht_cert_line_ids:
            raise UserError(_("No WHT certificate lines found."))
        
        # Create certificate
        cert_vals = {
            'partner_id': self.partner_id.id,
            'payment_id': self.payment_id.id,
            'date': self.payment_id.date,
            'state': 'draft',
            'income_tax_form': self.income_tax_form,
            'company_partner_id': self.payment_id.company_id.partner_id.id,
            'company_id': self.payment_id.company_id.id,
            'currency_id': self.payment_id.currency_id.id,
        }
        
        cert = self.env['withholding.tax.cert'].create(cert_vals)
        
        # Create certificate lines
        for line in self.wht_cert_line_ids:
            line_vals = {
                'cert_id': cert.id,
                'wht_cert_income_type': line.wht_cert_income_type,
                'base': line.base_amount,
                'amount': line.wht_amount,
            }
            
            if line.tax_id:
                wht_tax = self.env['account.withholding.tax'].search([
                    ('id', '=', line.tax_id.id)
                ], limit=1)
                if wht_tax:
                    line_vals['wht_tax_id'] = wht_tax.id
            
            self.env['withholding.tax.cert.line'].create(line_vals)
        
        # Return action to view created certificate
        return {
            'type': 'ir.actions.act_window',
            'name': 'WHT Certificate',
            'res_model': 'withholding.tax.cert',
            'res_id': cert.id,
            'view_mode': 'form',
            'target': 'current',
        }


class WhtCertGeneratorLine(models.TransientModel):
    _name = 'wht.cert.generator.line'
    _description = 'WHT Certificate Generator Line'
    
    wizard_id = fields.Many2one(
        'wht.cert.generator',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
    )
    
    base_amount = fields.Float(
        string='Base Amount',
        required=True,
    )
    
    wht_amount = fields.Float(
        string='WHT Amount',
        required=True,
    )
    
    wht_cert_income_type = fields.Selection(
        [
            ("1", "1. เงินเดือน ค่าจ้าง ฯลฯ 40(1)"),
            ("2", "2. ค่าธรรมเนียม ค่านายหน้า ฯลฯ 40(2)"),
            ("3", "3. ค่าแห่งลิขสิทธิ์ ฯลฯ 40(3)"),
            ("4A", "4. ดอกเบี้ย ฯลฯ 40(4)ก"),
            ("5", "5. ค่าจ้างทำของ ค่าบริการ ค่าเช่า ค่าขนส่ง ฯลฯ 3 เตรส"),
            ("6", "6. อื่นๆ (ระบุ)"),
        ],
        string='Type of Income',
        required=True,
        default='5',
    )
    
    tax_id = fields.Many2one(
        'account.tax',
        string='Tax',
    )
