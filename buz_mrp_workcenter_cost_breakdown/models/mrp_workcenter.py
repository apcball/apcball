# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    # Cost breakdown fields
    dl_per_hour = fields.Float(
        string='DL per Hour',
        help='Direct Labor cost per hour for this work center',
        default=0.0,
        required=False,
        digits='Product Price'
    )
    
    idl_per_hour = fields.Float(
        string='IDL per Hour',
        help='Indirect Labor cost per hour for this work center',
        default=0.0,
        required=False,
        digits='Product Price'
    )
    
    oh_per_hour = fields.Float(
        string='OH per Hour',
        help='Overhead cost per hour for this work center',
        default=0.0,
        required=False,
        digits='Product Price'
    )
    
    costs_hour = fields.Float(
        string='Cost per Hour',
        help='Total cost per hour (DL + IDL + OH)',
        compute='_compute_costs_hour',
        store=True,
        readonly=True,
        digits='Product Price'
    )
    
    @api.depends('dl_per_hour', 'idl_per_hour', 'oh_per_hour')
    def _compute_costs_hour(self):
        """
        Compute the total cost per hour by summing DL, IDL, and OH costs
        """
        for workcenter in self:
            workcenter.costs_hour = workcenter.dl_per_hour + workcenter.idl_per_hour + workcenter.oh_per_hour
    
    @api.constrains('dl_per_hour', 'idl_per_hour', 'oh_per_hour')
    def _check_cost_values(self):
        """
        Validation to prevent negative values in cost fields
        """
        for workcenter in self:
            if workcenter.dl_per_hour < 0:
                raise ValidationError(_('Direct Labor cost per hour cannot be negative.'))
            if workcenter.idl_per_hour < 0:
                raise ValidationError(_('Indirect Labor cost per hour cannot be negative.'))
            if workcenter.oh_per_hour < 0:
                raise ValidationError(_('Overhead cost per hour cannot be negative.'))