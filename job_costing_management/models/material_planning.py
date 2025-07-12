# -*- coding: utf-8 -*-

from odoo import models, fields, api


class MaterialPlanning(models.Model):
    _name = 'material.planning'
    _description = 'Material Planning'
    _order = 'planned_date, product_id'

    job_order_id = fields.Many2one('job.order', string='Job Order', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    description = fields.Char(string='Description')
    planned_qty = fields.Float(string='Planned Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    planned_date = fields.Date(string='Planned Date', default=fields.Date.today)
    notes = fields.Text(string='Notes')
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom_id = self.product_id.uom_id


class MaterialConsumption(models.Model):
    _name = 'material.consumption'
    _description = 'Material Consumption'
    _order = 'consumption_date desc, product_id'

    job_order_id = fields.Many2one('job.order', string='Job Order', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    description = fields.Char(string='Description')
    consumed_qty = fields.Float(string='Consumed Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    consumption_date = fields.Date(string='Consumption Date', default=fields.Date.today)
    location_id = fields.Many2one('stock.location', string='Location')
    notes = fields.Text(string='Notes')
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom_id = self.product_id.uom_id
