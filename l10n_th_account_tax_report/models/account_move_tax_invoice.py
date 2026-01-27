# Copyright 2026 Ecosoft Co., Ltd (https://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models


class AccountMoveTaxInvoice(models.Model):
    _inherit = "account.move.tax.invoice"

    # Fields for legacy data (imported from old system)
    tax_id = fields.Many2one(
        comodel_name="account.tax",
        string="Tax",
        help="Tax for legacy data without move_line_id",
    )
    tax_amount = fields.Monetary(
        string="Tax Amount",
        currency_field="company_currency_id",
        help="Tax amount for legacy data",
        default=0.0,
    )
    name = fields.Char(
        string="Description",
        help="Description for legacy data",
    )
    
    @api.depends('move_line_id')
    def _compute_account_id(self):
        """Override to support legacy data"""
        for rec in self:
            if rec.move_line_id:
                rec.account_id = rec.move_line_id.account_id
            # else: keep existing account_id for legacy data (don't override)
    
    @api.depends('move_id')
    def _compute_company_id(self):
        """Override to support legacy data"""
        for rec in self:
            if rec.move_id:
                rec.company_id = rec.move_id.company_id
            elif not rec.company_id:
                rec.company_id = self.env.company
    
    # Override fields to make them editable for legacy data
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Account",
        compute="_compute_account_id",
        store=True,
        readonly=False,
    )
    
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        compute="_compute_company_id",
        store=True,
        readonly=False,
        default=lambda self: self.env.company,
    )
    
    @api.model_create_multi
    def create(self, vals_list):
        """Auto-set company_id and tax_amount for legacy records"""
        for vals in vals_list:
            # Auto-set company_id if not provided for legacy records (no move_line_id)
            if not vals.get('move_line_id') and not vals.get('company_id'):
                vals['company_id'] = self.env.company.id
            
            # Auto-set tax_amount from balance if not provided for legacy records
            if not vals.get('move_line_id') and not vals.get('tax_amount') and vals.get('balance'):
                vals['tax_amount'] = vals['balance']
        
        return super().create(vals_list)
    
    def write(self, vals):
        """Auto-update tax_amount from balance for legacy records if needed"""
        result = super().write(vals)
        
        # If balance is updated for legacy records without tax_amount, update tax_amount
        if 'balance' in vals:
            for rec in self.filtered(lambda r: not r.move_line_id and not r.tax_amount):
                rec.tax_amount = rec.balance
        
        return result
