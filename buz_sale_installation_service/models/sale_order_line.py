# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    include_installation = fields.Boolean(
        string='Include Installation',
        default=False,
        help='Check to automatically add installation service line'
    )
    
    is_installation_line = fields.Boolean(
        string='Is Installation Line',
        default=False,
        readonly=True,
        help='Technical field to identify installation service lines'
    )
    
    installation_parent_line_id = fields.Many2one(
        'sale.order.line',
        string='Installation Parent Line',
        readonly=True,
        ondelete='cascade',
        help='Parent product line for this installation service'
    )
    
    installation_child_line_id = fields.Many2one(
        'sale.order.line',
        string='Installation Child Line',
        readonly=True,
        ondelete='set null',
        help='Installation service line created from this product line'
    )
    
    installation_fee = fields.Monetary(
        string='Installation Fee',
        related='product_template_id.installation_fee',
        store=True,
        readonly=True
    )

    @api.constrains('is_installation_line')
    def _check_installation_line_creation(self):
        """Prevent manual creation of installation lines"""
        for line in self:
            if line.is_installation_line and not line.installation_parent_line_id:
                raise ValidationError(
                    'Installation service lines cannot be created manually. '
                    'Please use the "Include Installation" checkbox on the product line.'
                )

    @api.onchange('product_id')
    def _onchange_product_id_installation(self):
        """Reset installation when product changes"""
        if self.product_id:
            # Remove old installation line if exists
            if self.installation_child_line_id:
                self.installation_child_line_id.unlink()
                self.installation_child_line_id = False
            
            # Reset include_installation flag
            self.include_installation = False

    @api.onchange('include_installation')
    def _onchange_include_installation(self):
        """Validate and warn user about installation line"""
        if not self.product_id or self.is_installation_line:
            return

        if self.include_installation:
            # Check if installation fee is set
            if not self.installation_fee or self.installation_fee <= 0:
                self.include_installation = False
                return {
                    'warning': {
                        'title': 'No Installation Fee',
                        'message': 'This product has no installation fee configured.'
                    }
                }
            
            # Get installation service product
            service_product = self._get_installation_service_product()
            if not service_product:
                self.include_installation = False
                return {
                    'warning': {
                        'title': 'Configuration Required',
                        'message': 'Please configure installation service product in product settings or company settings.'
                    }
                }

    @api.onchange('product_uom_qty')
    def _onchange_product_uom_qty_installation(self):
        """Sync quantity to installation line"""
        if self.installation_child_line_id and not self.is_installation_line:
            self.installation_child_line_id.product_uom_qty = self.product_uom_qty

    def _get_installation_service_product(self):
        """Get installation service product from product or company default"""
        self.ensure_one()
        
        # Try product-specific service product first
        if self.product_id.installation_service_product_id:
            return self.product_id.installation_service_product_id
        
        # Fall back to company default
        company = self.order_id.company_id
        if company.default_installation_service_product_id:
            return company.default_installation_service_product_id
        
        # Try to get the default product from data and auto-configure
        default_product = self.env.ref('buz_sale_installation_service.product_installation_service', raise_if_not_found=False)
        if default_product:
            # Auto-set as company default
            company.sudo().write({'default_installation_service_product_id': default_product.id})
            return default_product
        
        return False

    def _create_installation_line(self, service_product):
        """Create installation service line"""
        self.ensure_one()
        
        if self.is_installation_line:
            return
        
        # Calculate sequence to show installation line right after product line
        next_sequence = self.sequence + 1
        
        # Create installation line values
        installation_vals = {
            'order_id': self.order_id.id,
            'product_id': service_product.id,
            'name': f'↳ Installation service for {self.product_id.display_name}',
            'product_uom_qty': self.product_uom_qty,
            'product_uom': service_product.uom_id.id,
            'price_unit': self.installation_fee,
            'tax_id': [(6, 0, service_product.taxes_id.ids)],
            'sequence': next_sequence,
            'is_installation_line': True,
            'installation_parent_line_id': self.id,
            'display_type': False,
        }
        
        # Create the line
        installation_line = self.create(installation_vals)
        self.installation_child_line_id = installation_line
        
        # Update sequences of following lines
        self._update_following_sequences(next_sequence)

    def _update_following_sequences(self, after_sequence):
        """Update sequences of lines that come after the installation line"""
        following_lines = self.order_id.order_line.filtered(
            lambda l: l.sequence > after_sequence and l != self.installation_child_line_id
        )
        for line in following_lines:
            line.sequence += 1

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle installation line creation"""
        lines = super(SaleOrderLine, self).create(vals_list)
        
        # Create installation lines for lines that need them
        for line in lines:
            if line.include_installation and not line.is_installation_line and not line.installation_child_line_id:
                if line.installation_fee and line.installation_fee > 0:
                    service_product = line._get_installation_service_product()
                    if service_product:
                        line._create_installation_line(service_product)
        
        return lines

    def write(self, vals):
        """Override write to handle installation line synchronization"""
        # Prevent direct deletion of installation lines
        if 'product_id' in vals or 'active' in vals:
            for line in self:
                if line.is_installation_line:
                    raise UserError(
                        'Installation service lines cannot be modified or deleted directly. '
                        'Please uncheck "Include Installation" on the parent product line.'
                    )
        
        # Handle include_installation changes
        if 'include_installation' in vals:
            for line in self:
                if line.is_installation_line:
                    continue
                    
                if vals['include_installation'] and not line.installation_child_line_id:
                    # Create installation line
                    if line.installation_fee and line.installation_fee > 0:
                        service_product = line._get_installation_service_product()
                        if service_product:
                            line._create_installation_line(service_product)
                elif not vals['include_installation'] and line.installation_child_line_id:
                    # Remove installation line
                    line.installation_child_line_id.with_context(force_delete_installation=True).sudo().unlink()
        
        # Handle quantity changes
        if 'product_uom_qty' in vals:
            for line in self:
                if line.installation_child_line_id and not line.is_installation_line:
                    line.installation_child_line_id.write({'product_uom_qty': vals['product_uom_qty']})
        
        result = super(SaleOrderLine, self).write(vals)
        
        return result

    def unlink(self):
        """Override unlink to cascade delete installation lines or prevent deletion"""
        for line in self:
            if line.is_installation_line:
                raise UserError(
                    'Installation service lines cannot be deleted directly. '
                    'Please uncheck "Include Installation" on the parent product line.'
                )
            
            # Delete child installation line when parent is deleted
            if line.installation_child_line_id:
                # Temporarily allow deletion of installation line
                line.installation_child_line_id.with_context(
                    force_delete_installation=True
                ).sudo().unlink()
        
        return super(SaleOrderLine, self).unlink()

    def _check_line_unlink(self):
        """Allow unlinking installation lines when forced"""
        if self.env.context.get('force_delete_installation'):
            return
        return super(SaleOrderLine, self)._check_line_unlink()
