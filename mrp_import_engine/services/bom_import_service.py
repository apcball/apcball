# -*- coding: utf-8 -*-
from odoo import models, api, _
import json

class BomImportService(models.AbstractModel):
    _name = 'mrp.import.bom.service'
    _description = 'BOM Import Service'

    @api.model
    def process_session(self, session_id):
        session = self.env['mrp.import.session'].browse(session_id)
        if not session.exists():
            return
        
        stagings = session.bom_staging_ids
        success_count = 0
        failed_count = 0
        
        # Pre-fetch products to optimize queries
        default_codes = stagings.mapped('product_default_code') + stagings.mapped('line_ids.component_default_code')
        products = self.env['product.product'].search([('default_code', 'in', list(set(default_codes)))])
        product_map = {p.default_code: p.id for p in products}

        # Track existing BOMs to prevent duplicates if necessary (omitted for brevity, depending on business rules)
        
        for idx, staging in enumerate(stagings):
            try:
                with self.env.cr.savepoint():
                    # Validation layer
                    if staging.product_default_code not in product_map:
                        raise ValueError(_("Product code %s not found") % staging.product_default_code)
                    if staging.product_qty <= 0:
                        raise ValueError(_("Product quantity must be positive"))
                    
                    product_record = self.env['product.product'].browse(product_map[staging.product_default_code])
                    bom_vals = {
                        'product_tmpl_id': product_record.product_tmpl_id.id,
                        'product_id': product_record.id,
                        'product_qty': staging.product_qty,
                        'product_uom_id': product_record.uom_id.id,
                        'type': staging.bom_type,
                        'code': staging.bom_code,
                    }
                    bom = self.env['mrp.bom'].create(bom_vals)
                    
                    # Setup operations: only for normal manufacture BOMs (Kits do not support routing)
                    op_map = {}
                    if staging.bom_type != 'phantom':
                        for line in staging.line_ids:
                            if line.operation and line.operation not in op_map:
                                wc = self.env['mrp.workcenter'].search(['|', ('name', '=', line.operation), ('code', '=', line.operation)], limit=1)
                                if wc:
                                    op = self.env['mrp.routing.workcenter'].create({
                                        'name': line.operation,
                                        'workcenter_id': wc.id,
                                        'bom_id': bom.id,
                                    })
                                    op_map[line.operation] = op.id

                    for line in staging.line_ids:
                        if line.component_default_code not in product_map:
                            raise ValueError(_("Component code %s not found") % line.component_default_code)
                        if line.quantity <= 0:
                            raise ValueError(_("Component quantity must be positive"))
                            
                        comp_product = self.env['product.product'].browse(product_map[line.component_default_code])
                        uom_id = comp_product.uom_id.id
                        if line.uom:
                            # Try to match uom name perfectly
                            uom_record = self.env['uom.uom'].search([('name', '=ilike', line.uom)], limit=1)
                            if uom_record:
                                uom_id = uom_record.id
                                
                        self.env['mrp.bom.line'].create({
                            'bom_id': bom.id,
                            'product_id': comp_product.id,
                            'product_qty': line.quantity,
                            'product_uom_id': uom_id,
                            'operation_id': op_map.get(line.operation, False) if line.operation else False,
                        })
                    
                staging.state = 'done'
                success_count += 1
                
                self.env['mrp.import.log'].create({
                    'session_id': session.id,
                    'row_number': idx + 1,
                    'data_json': json.dumps({'bom_code': staging.bom_code}),
                    'state': 'success',
                })
                
            except Exception as e:
                staging.state = 'failed'
                failed_count += 1
                self.env['mrp.import.log'].create({
                    'session_id': session.id,
                    'row_number': idx + 1,
                    'data_json': json.dumps({'bom_code': staging.bom_code, 'product_default_code': staging.product_default_code}),
                    'state': 'failed',
                    'message': str(e),
                })
                
        session.write({
            'state': 'done',
            'success_records': success_count,
            'failed_records': failed_count,
            'total_records': len(stagings)
        })
