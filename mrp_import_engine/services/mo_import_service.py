# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
import json

class MoImportService(models.AbstractModel):
    _name = 'mrp.import.mo.service'
    _description = 'MO Import Service'

    @api.model
    def process_session(self, session_id):
        session = self.env['mrp.import.session'].browse(session_id)
        if not session.exists():
            return
        
        stagings = session.mo_staging_ids
        success_count = 0
        failed_count = 0
        
        default_codes = stagings.mapped('product_default_code')
        products = self.env['product.product'].search([('default_code', 'in', list(set(default_codes)))])
        product_map = {p.default_code: p.id for p in products}

        # Handle Replay engine natively
        # Replay rule: if mo_name / external_ref matches an existing MO from the same batch, we can cancel & rebuild if needed,
        # but for simplicity, we focus on straightforward creation.

        for idx, staging in enumerate(stagings):
            try:
                with self.env.cr.savepoint():
                    # Validation layer
                    if staging.product_default_code not in product_map:
                        raise ValueError(_("Product code %s not found") % staging.product_default_code)
                    if staging.product_qty <= 0:
                        raise ValueError(_("Product quantity must be positive"))
                    
                    product_id = product_map[staging.product_default_code]
                    
                    # Auto find BOM
                    bom = self.env['mrp.bom'].search(['|', ('code', '=', staging.bom_code), ('product_id', '=', product_id)], limit=1)
                    # Fallback to product_tmpl_id
                    if not bom:
                        product_tmpl_id = self.env['product.product'].browse(product_id).product_tmpl_id.id
                        bom = self.env['mrp.bom'].search([('product_tmpl_id', '=', product_tmpl_id)], limit=1)

                    if not bom:
                        raise ValueError(_("No BOM found for product %s") % staging.product_default_code)

                    # Replay Logic: if MO with external_ref exists, delete or bypass
                    existing_mo = self.env['mrp.production'].search([('external_ref', '=', staging.mo_name)], limit=1)
                    if existing_mo:
                        if existing_mo.state in ('draft', 'cancel'):
                            existing_mo.unlink()
                        else:
                            raise ValueError(_("MO %s already exists and is not droppable.") % staging.mo_name)
                    
                    mo_vals = {
                        'name': staging.mo_name,
                        'product_id': product_id,
                        'product_qty': staging.product_qty,
                        'bom_id': bom.id,
                        'external_ref': staging.mo_name,
                        'import_session_id': session.id,
                        'date_start': staging.planned_start_date or fields.Datetime.now(),
                        'date_deadline': staging.planned_finish_date or fields.Datetime.now(),
                    }
                    if staging.operation_type:
                        picking_type = self.env['stock.picking.type'].search([('name', '=ilike', staging.operation_type)], limit=1)
                        if picking_type:
                            mo_vals['picking_type_id'] = picking_type.id
                            
                    mo = self.env['mrp.production'].create(mo_vals)

                
                mo._onchange_bom_id()
                mo.action_confirm()

                staging.state = 'done'
                success_count += 1
                
                self.env['mrp.import.log'].create({
                    'session_id': session.id,
                    'row_number': idx + 1,
                    'data_json': json.dumps({'mo_name': staging.mo_name}),
                    'state': 'success',
                })
                
            except Exception as e:
                staging.state = 'failed'
                failed_count += 1
                self.env['mrp.import.log'].create({
                    'session_id': session.id,
                    'row_number': idx + 1,
                    'data_json': json.dumps({'mo_name': staging.mo_name, 'product_default_code': staging.product_default_code}),
                    'state': 'failed',
                    'message': str(e),
                })
                
        session.write({
            'state': 'done',
            'success_records': success_count,
            'failed_records': failed_count,
            'total_records': len(stagings)
        })
