# -*- coding: utf-8 -*-
from odoo import api, fields, models

class MrpBomStaging(models.Model):
    _name = 'mrp.bom.staging'
    _description = 'MRP BOM Staging'

    session_id = fields.Many2one('mrp.import.session', ondelete='cascade')
    bom_code = fields.Char(string='BOM Code', required=True)
    product_default_code = fields.Char(string='Product Code', required=True)
    product_qty = fields.Float(string='Product Qty', default=1.0)
    bom_type = fields.Selection([('normal', 'Manufacture this product'), ('phantom', 'Kit')], default='normal')
    version = fields.Char(string='Version')
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done'), ('failed', 'Failed')], default='draft')
    
    line_ids = fields.One2many('mrp.bom.line.staging', 'bom_staging_id', string='Staging Lines')


class MrpBomLineStaging(models.Model):
    _name = 'mrp.bom.line.staging'
    _description = 'MRP BOM Line Staging'

    bom_staging_id = fields.Many2one('mrp.bom.staging', ondelete='cascade')
    bom_code = fields.Char(string='BOM Code')
    component_default_code = fields.Char(string='Component Code', required=True)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    uom = fields.Char(string='UoM')
    operation = fields.Char(string='Operation')


class MrpMoStaging(models.Model):
    _name = 'mrp.mo.staging'
    _description = 'MRP MO Staging'

    session_id = fields.Many2one('mrp.import.session', ondelete='cascade')
    mo_name = fields.Char(string='MO Name', required=True)
    product_default_code = fields.Char(string='Product Code', required=True)
    product_qty = fields.Float(string='Product Qty', required=True, default=1.0)
    bom_code = fields.Char(string='BOM Code')
    bom_type = fields.Selection([('normal', 'Manufacture this product'), ('phantom', 'Kit')], default='normal')
    operation_type = fields.Char(string='Operation Type')
    work_center = fields.Char(string='Work Center')
    planned_start_date = fields.Datetime(string='Planned Start Date')
    planned_finish_date = fields.Datetime(string='Planned Finish Date')
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done'), ('failed', 'Failed')], default='draft')

    line_ids = fields.One2many('mrp.mo.line.staging', 'mo_staging_id', string='Staging Lines')


class MrpMoLineStaging(models.Model):
    _name = 'mrp.mo.line.staging'
    _description = 'MRP MO Line Staging'

    mo_staging_id = fields.Many2one('mrp.mo.staging', ondelete='cascade')
    mo_name = fields.Char(string='MO Name')
    component_default_code = fields.Char(string='Component Code', required=True)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
