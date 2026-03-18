# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    bom_id = fields.Many2one(
        'mrp.bom', 
        string='BOM Version',
        domain="[('product_tmpl_id', '=', product_template_id), ('company_id', 'in', [False, company_id]), ('active', '=', True)]"
    )
    bom_override = fields.Boolean(string='BOM Override', default=False, copy=False)
    bom_type = fields.Selection(related='bom_id.type', store=True)
    bom_code = fields.Char(related='bom_id.code', string='BOM Code')

    @api.onchange('product_id', 'company_id')
    def _onchange_product_id_set_bom(self):
        for line in self:
            if not line.product_template_id:
                if not line.bom_override:
                    line.bom_id = False
                continue
            
            # Find candidate BOMs
            boms = self.env['mrp.bom'].search([
                ('product_tmpl_id', '=', line.product_template_id.id),
                ('company_id', 'in', [False, line.company_id.id]),
                ('active', '=', True)
            ])
            
            if line.order_id.bom_version_id and not line.bom_override:
                line.bom_id = line.order_id.bom_version_id.id
            elif len(boms) == 1 and not line.bom_override:
                line.bom_id = boms.id
            elif not line.bom_override:
                line.bom_id = False

    @api.onchange('bom_id')
    def _onchange_bom_id_check_override(self):
        for line in self:
            if line.order_id.bom_version_id:
                if line.bom_id and line.bom_id != line.order_id.bom_version_id:
                    line.bom_override = True
                elif line.bom_id == line.order_id.bom_version_id:
                    line.bom_override = False
            else:
                line.bom_override = bool(line.bom_id)

    def _prepare_procurement_values(self, group_id=False):
        res = super(SaleOrderLine, self)._prepare_procurement_values(group_id=group_id)
        effective_bom = self.bom_id or self.order_id.bom_version_id
        if effective_bom:
            res['bom_id'] = effective_bom.id
        return res
