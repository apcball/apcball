# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    commercial_invoice_enabled = fields.Boolean(
        string='Generate Commercial Invoice',
        default=False,
        tracking=True,
        help='Check this to generate a Commercial Invoice number for this Sales Order'
    )
    
    commercial_invoice_number = fields.Char(
        string='Commercial Invoice No.',
        readonly=True,
        copy=False,
        tracking=True,
    )

    packing_list_enabled = fields.Boolean(
        string='Generate Packing List',
        default=False,
        tracking=True,
        help='Check this to generate a Packing List number for this Sales Order'
    )
    
    packing_list_number = fields.Char(
        string='Packing List No.',
        readonly=True,
        copy=False,
        tracking=True,
    )

    incoterms_id = fields.Many2one(
        'account.incoterms',
        string='Incoterms',
        tracking=True,
    )
    loading_date = fields.Date(
        string='Loading Date',
        tracking=True,
    )
    shipping_mark = fields.Char(
        string='Shipping Mark',
        tracking=True,
    )
    shipping_by = fields.Selection([
        ('air', 'By Air'),
        ('sea', 'By Sea'),
        ('land', 'By Land'),
    ], string='Shipping By', tracking=True)
    bank_info = fields.Text(
        string='Bank Information',
        tracking=True,
    )

    amount_text = fields.Char(
        string='Amount in Words',
        compute='_compute_amount_text',
        store=True,
    )

    show_hscode = fields.Boolean(
        string='Show HS CODE in Report',
        default=False,
        tracking=True,
        help='Check this to display HS CODE column in packing list report'
    )

    @api.depends('amount_total', 'currency_id')
    def _compute_amount_text(self):
        """Compute the total amount in words."""
        for record in self:
            if record.currency_id:
                record.amount_text = record.currency_id.amount_to_text(record.amount_total)
            else:
                record.amount_text = ''

    @api.model_create_multi
    def create(self, vals_list):
        """Override create method to generate CIV and PL numbers when enabled."""
        for vals in vals_list:
            if vals.get('commercial_invoice_enabled') and not vals.get('commercial_invoice_number'):
                vals['commercial_invoice_number'] = self._get_commercial_invoice_number()
            if vals.get('packing_list_enabled') and not vals.get('packing_list_number'):
                vals['packing_list_number'] = self._get_packing_list_number()
        return super().create(vals_list)

    def _get_commercial_invoice_number(self):
        """Get next commercial invoice number from sequence."""
        return self.env['ir.sequence'].next_by_code('commercial.invoice.sequence')

    def _get_packing_list_number(self):
        """Get next packing list number from sequence."""
        return self.env['ir.sequence'].next_by_code('packing.list.sequence')

    def write(self, vals):
        """Override write method to generate CIV and PL numbers when checkboxes are enabled."""
        for record in self:
            if 'commercial_invoice_enabled' in vals and vals['commercial_invoice_enabled'] and not record.commercial_invoice_number:
                vals['commercial_invoice_number'] = self._get_commercial_invoice_number()
            if 'packing_list_enabled' in vals and vals['packing_list_enabled'] and not record.packing_list_number:
                vals['packing_list_number'] = self._get_packing_list_number()
        return super().write(vals)

    def action_print_commercial_invoice(self):
        """Action to print commercial invoice from sale order."""
        self.ensure_one()
        if not self.commercial_invoice_enabled:
            raise UserError(_("Commercial Invoice is not enabled for this sales order."))
        if not self.commercial_invoice_number:
            raise UserError(_("Commercial Invoice number was not generated. Please enable the Commercial Invoice checkbox."))
        return self.env.ref('buz_commercial_invoice.action_report_commercial_invoice').report_action(self)

    def action_print_packing_list(self):
        """Action to print packing list from sale order."""
        self.ensure_one()
        if not self.packing_list_enabled:
            raise UserError(_("Packing List is not enabled for this sales order."))
        if not self.packing_list_number:
            raise UserError(_("Packing List number was not generated. Please enable the Packing List checkbox."))
        return self.env.ref('buz_commercial_invoice.action_report_packing_list').report_action(self)

    def get_bom_components(self, product, quantity, line_hscode=''):
        """
        Get BOM components for a product.
        Returns a list of dictionaries with component details.
        If no BOM exists, returns an empty list.
        """
        self.ensure_one()
        # Search for BOM manually to avoid API compatibility issues
        bom = self.env['mrp.bom'].search([
            '|',
            ('product_id', '=', product.id),
            '&',
            ('product_id', '=', False),
            ('product_tmpl_id', '=', product.product_tmpl_id.id),
            ('company_id', 'in', [self.company_id.id, False]),
            ('type', '=', 'normal')
        ], limit=1)
        
        if not bom:
            return []
        
        components = []
        for line in bom.bom_line_ids:
            component_qty = (line.product_qty / bom.product_qty) * quantity
            components.append({
                'product': line.product_id,
                'quantity': component_qty,
                'uom': line.product_uom_id,
                'hscode': line_hscode,  # Use parent line's HS CODE for components
            })
        return components

    def get_total_bom_quantity(self):
        """Calculate total quantity including BOM components."""
        self.ensure_one()
        total = 0.0
        for line in self.order_line:
            bom_components = self.get_bom_components(line.product_id, line.product_uom_qty)
            if bom_components:
                for component in bom_components:
                    total += component['quantity']
            else:
                total += line.product_qty
        return total

    def get_total_bom_gross_weight(self):
        """Calculate total gross weight including BOM components."""
        self.ensure_one()
        total = 0.0
        for line in self.order_line:
            bom_components = self.get_bom_components(line.product_id, line.product_uom_qty)
            if bom_components:
                for component in bom_components:
                    total += component['quantity'] * component['product'].box_weight
            else:
                total += line.product_uom_qty * line.product_id.box_weight
        return total

    def get_total_bom_net_weight(self):
        """Calculate total net weight including BOM components."""
        self.ensure_one()
        total = 0.0
        for line in self.order_line:
            bom_components = self.get_bom_components(line.product_id, line.product_uom_qty)
            if bom_components:
                for component in bom_components:
                    total += component['quantity'] * component['product'].weight
            else:
                total += line.product_uom_qty * line.product_id.weight
        return total

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    hscode = fields.Char(
        string='HS CODE',
        help='Harmonized System Code for customs'
    )

