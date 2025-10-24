from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WarrantyInvoiceWizard(models.TransientModel):
    _name = 'warranty.invoice.wizard'
    _description = 'Warranty Invoice Wizard'

    claim_id = fields.Many2one(
        'warranty.claim',
        string='Warranty Claim',
        required=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        domain="[('type', '=', 'sale')]"
    )
    invoice_date = fields.Date(
        string='Invoice Date',
        default=fields.Date.today,
        required=True
    )
    line_ids = fields.One2many(
        'warranty.invoice.line',
        'wizard_id',
        string='Invoice Lines'
    )
    notes = fields.Text(string='Notes')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        # Set default journal
        journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        if journal:
            res['journal_id'] = journal.id
        
        # Load claim lines
        if 'claim_id' in self._context:
            claim = self.env['warranty.claim'].browse(self._context['claim_id'])
            lines = []
            for claim_line in claim.claim_line_ids:
                if claim_line.unit_price > 0:
                    lines.append((0, 0, {
                        'product_id': claim_line.product_id.id,
                        'description': claim_line.description,
                        'qty': claim_line.qty,
                        'unit_price': claim_line.unit_price,
                    }))
            if lines:
                res['line_ids'] = lines
        
        return res

    def action_create_invoice(self):
        self.ensure_one()
        
        if not self.line_ids:
            raise UserError(_('Please add at least one invoice line.'))
        
        # Create invoice
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'journal_id': self.journal_id.id,
            'invoice_date': self.invoice_date,
            'invoice_origin': self.claim_id.name,
            'narration': self.notes,
            'invoice_line_ids': [],
        }
        
        for line in self.line_ids:
            invoice_line_vals = {
                'product_id': line.product_id.id,
                'name': line.description or line.product_id.name,
                'quantity': line.qty,
                'price_unit': line.unit_price,
                'product_uom_id': line.product_id.uom_id.id,
            }
            
            # Get income account
            if line.product_id.property_account_income_id:
                invoice_line_vals['account_id'] = line.product_id.property_account_income_id.id
            elif line.product_id.categ_id.property_account_income_categ_id:
                invoice_line_vals['account_id'] = line.product_id.categ_id.property_account_income_categ_id.id
            
            invoice_vals['invoice_line_ids'].append((0, 0, invoice_line_vals))
        
        invoice = self.env['account.move'].create(invoice_vals)
        
        # Link invoice to claim
        self.claim_id.write({
            'invoice_ids': [(4, invoice.id)],
        })
        
        # Post message
        self.claim_id.message_post(
            body=_('Invoice created: %s', invoice.name),
            subject=_('Invoice Created')
        )
        
        return {
            'name': _('Customer Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }


class WarrantyInvoiceLine(models.TransientModel):
    _name = 'warranty.invoice.line'
    _description = 'Warranty Invoice Line'

    wizard_id = fields.Many2one(
        'warranty.invoice.wizard',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    description = fields.Char(string='Description')
    qty = fields.Float(
        string='Quantity',
        default=1.0,
        required=True
    )
    unit_price = fields.Monetary(
        string='Unit Price',
        currency_field='currency_id',
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.unit_price = self.product_id.list_price
