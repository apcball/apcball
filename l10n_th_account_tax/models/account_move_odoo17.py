# Copyright 2019 Ecosoft Co., Ltd (http://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Simplified withholding tax integration for Odoo 17
    withholding_tax_id = fields.Many2one(
        comodel_name="account.tax",
        string="Withholding Tax",
        domain=[('is_withholding_tax', '=', True)],
        help="Select withholding tax if applicable",
    )
    
    withholding_tax_amount = fields.Monetary(
        string="Withholding Tax Amount",
        compute="_compute_withholding_tax_amount",
        store=True,
    )
    
    withholding_base_amount = fields.Monetary(
        string="Withholding Base Amount",
        compute="_compute_withholding_tax_amount",
        store=True,
    )

    @api.depends('withholding_tax_id', 'price_total')
    def _compute_withholding_tax_amount(self):
        for line in self:
            if line.withholding_tax_id and line.price_total:
                line.withholding_base_amount = abs(line.price_total)
                line.withholding_tax_amount = abs(line.price_total) * (line.withholding_tax_id.amount / 100)
            else:
                line.withholding_base_amount = 0
                line.withholding_tax_amount = 0


class AccountMove(models.Model):
    _inherit = "account.move"

    # Add withholding tax summary fields
    total_withholding_tax = fields.Monetary(
        string="Total Withholding Tax",
        compute="_compute_withholding_totals",
        store=True,
    )
    
    total_withholding_base = fields.Monetary(
        string="Total Withholding Base",
        compute="_compute_withholding_totals", 
        store=True,
    )

    @api.depends('line_ids.withholding_tax_amount', 'line_ids.withholding_base_amount')
    def _compute_withholding_totals(self):
        for move in self:
            move.total_withholding_tax = sum(move.line_ids.mapped('withholding_tax_amount'))
            move.total_withholding_base = sum(move.line_ids.mapped('withholding_base_amount'))

    def _post(self, soft=True):
        """Create withholding tax entries when posting"""
        result = super()._post(soft=soft)
        
        for move in self:
            # Create withholding tax journal entries
            wht_lines = move.line_ids.filtered('withholding_tax_id')
            if wht_lines:
                move._create_withholding_tax_entries(wht_lines)
        
        return result

    def _create_withholding_tax_entries(self, wht_lines):
        """Create withholding tax journal entries"""
        for line in wht_lines:
            if line.withholding_tax_amount and line.withholding_tax_id.withholding_account_id:
                # Create withholding tax payable entry
                wht_move_line_vals = {
                    'move_id': self.id,
                    'account_id': line.withholding_tax_id.withholding_account_id.id,
                    'name': f'WHT: {line.withholding_tax_id.name}',
                    'credit': line.withholding_tax_amount if self.move_type in ['in_invoice', 'out_refund'] else 0,
                    'debit': line.withholding_tax_amount if self.move_type in ['out_invoice', 'in_refund'] else 0,
                    'partner_id': line.partner_id.id,
                }
                
                # Create corresponding entry to reduce payable/receivable
                balance_account = line.account_id
                balance_move_line_vals = {
                    'move_id': self.id,
                    'account_id': balance_account.id,
                    'name': f'WHT Adjustment: {line.withholding_tax_id.name}',
                    'debit': line.withholding_tax_amount if self.move_type in ['in_invoice', 'out_refund'] else 0,
                    'credit': line.withholding_tax_amount if self.move_type in ['out_invoice', 'in_refund'] else 0,
                    'partner_id': line.partner_id.id,
                }
                
                # Create the journal entries
                self.env['account.move.line'].create([wht_move_line_vals, balance_move_line_vals])
