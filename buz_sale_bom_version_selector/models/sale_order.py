# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    bom_version_id = fields.Many2one(
        'mrp.bom',
        string='BOM Version',
        domain="[('active', '=', True), ('company_id', 'in', [False, company_id])]",
        help="Acts as a default BOM Version for all lines. Can be overridden per line."
    )

    @api.onchange('bom_version_id')
    def _onchange_bom_version_id(self):
        for order in self:
            for line in order.order_line:
                if not line.bom_override and line.state in ['draft', 'sent']:
                    line.bom_id = order.bom_version_id.id

    def action_confirm(self):
        # Optimize performance with prefetching
        self.mapped('order_line.product_id.product_tmpl_id')
        self.mapped('order_line.product_id.route_ids')

        for order in self:
            log_lines = []
            for line in order.order_line:
                if not line.product_id or line.display_type:
                    continue
                
                # Check if product has BOMs
                boms = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', line.product_template_id.id),
                    ('company_id', 'in', [False, line.company_id.id]),
                    ('active', '=', True)
                ])
                
                effective_bom = line.bom_id or order.bom_version_id
                
                # Validation: multiple BOMs and none resolved
                if boms and len(boms) > 1 and not effective_bom:
                    raise ValidationError(_(
                        "Product '%s' has multiple BOMs. Please select a BOM Version on the Sale Order Line or set a default BOM Version on the header."
                    ) % line.product_id.display_name)
                
                if effective_bom:
                    # Basic route incompatibility check (Kit vs Service)
                    if effective_bom.type == 'phantom' and line.product_id.type == 'service':
                        raise ValidationError(_(
                            "BOM Version '%s' is a Kit (Phantom), but product '%s' is a Service. This is incompatible."
                        ) % (effective_bom.display_name, line.product_id.display_name))
                    
                    override_text = " (Override)" if line.bom_override else ""
                    log_lines.append(f"- {line.product_id.display_name} \u2192 {effective_bom.display_name}{override_text}")
                    
            if log_lines:
                log_msg = _("<b>BOM Version applied:</b><br/>%s") % "<br/>".join(log_lines)
                order.message_post(body=log_msg)
        
        return super(SaleOrder, self).action_confirm()
