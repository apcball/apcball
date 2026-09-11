# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AddToPoolWizard(models.TransientModel):
    _name = 'add.to.pool.wizard'
    _description = 'Add MR Lines to Procurement Pool'

    requisition_id = fields.Many2one(
        'material.requisition', string='Material Requisition',
        required=True, readonly=True)

    pool_id = fields.Many2one(
        'procurement.pool', string='Procurement Pool',
        domain="[('state', '=', 'draft')]",
        help='Select an existing pool or leave empty to create a new one.')

    create_new_pool = fields.Boolean(
        string='Create New Pool', default=False)

    mr_line_ids = fields.Many2many(
        'material.requisition.line',
        string='MR Lines to Add',
        domain="[('requisition_id', '=', requisition_id), "
               "('requisition_action', '=', 'purchase'), "
               "('is_pooled', '=', False)]")

    @api.onchange('create_new_pool')
    def _onchange_create_new_pool(self):
        if self.create_new_pool:
            self.pool_id = False

    def action_add_to_pool(self):
        """Add selected MR lines to the procurement pool."""
        self.ensure_one()

        if not self.mr_line_ids:
            raise ValidationError(_('Please select at least one MR line.'))

        # Create or get pool
        if self.create_new_pool or not self.pool_id:
            pool = self.env['procurement.pool'].create({
                'company_id': self.requisition_id.company_id.id,
                'notes': _('Created from %s') % self.requisition_id.name,
            })
        else:
            pool = self.pool_id

        PoolLine = self.env['procurement.pool.line']

        for mr_line in self.mr_line_ids:
            # Determine vendor: from MR line, or product's preferred vendor
            vendor = mr_line.vendor_id
            if not vendor and mr_line.product_id.seller_ids:
                vendor = mr_line.product_id.seller_ids[0].partner_id

            # Determine analytic distribution and department from MR line
            analytic_dist = mr_line.analytic_distribution
            dept = mr_line.requisition_id.department_id

            # Check if a pool line for this product+vendor+department already exists
            existing_pool_line = pool.line_ids.filtered(
                lambda l, p=mr_line.product_id, u=mr_line.uom_id, v=vendor, d=dept:
                    l.product_id == p and l.uom_id == u and l.vendor_id == v and l.department_id == d)

            if existing_pool_line:
                # Add the MR line to existing pool line
                existing_pool_line[0].write({
                    'mr_line_ids': [(4, mr_line.id)],
                })
                # Set analytic if not already set
                if not existing_pool_line[0].analytic_distribution and analytic_dist:
                    existing_pool_line[0].analytic_distribution = analytic_dist
            else:
                # Create new pool line
                vals = {
                    'pool_id': pool.id,
                    'product_id': mr_line.product_id.id,
                    'uom_id': mr_line.uom_id.id,
                    'description': mr_line.description,
                    'price_unit': mr_line.estimated_cost or mr_line.product_id.standard_price,
                    'mr_line_ids': [(4, mr_line.id)],
                }
                if vendor:
                    vals['vendor_id'] = vendor.id
                if dept:
                    vals['department_id'] = dept.id
                if analytic_dist:
                    vals['analytic_distribution'] = analytic_dist
                PoolLine.create(vals)

        # Post message on the MR
        self.requisition_id.write({'state': 'ordered'})
        self.requisition_id.message_post(
            body=_('Lines added to Procurement Pool: <a href="#" '
                   'data-oe-model="procurement.pool" data-oe-id="%d">%s</a>')
            % (pool.id, pool.name))

        return {
            'name': _('Procurement Pool'),
            'type': 'ir.actions.act_window',
            'res_model': 'procurement.pool',
            'res_id': pool.id,
            'view_mode': 'form',
            'target': 'current',
        }
