# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ITCategory(models.Model):
    _name = 'it.category'
    _description = 'IT Ticket Category'
    _order = 'name'

    name = fields.Char(string='Category Name', required=True, translate=True)
    description = fields.Text(string='Description', translate=True)
    ticket_type = fields.Selection([
        ('incident', 'Incident'),
        ('service', 'Service Request'),
        ('purchase', 'Purchase Request'),
    ], string='Ticket Type', required=True, default='incident')
    parent_id = fields.Many2one('it.category', string='Parent Category')
    child_ids = fields.One2many('it.category', 'parent_id', string='Child Categories')
    team_id = fields.Many2one('res.users', string='Default Team')
    active = fields.Boolean(string='Active', default=True)
    color = fields.Integer(string='Color Index', default=0)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    
    @api.depends('name', 'parent_id.name')
    def _compute_display_name(self):
        for category in self:
            if category.parent_id:
                category.display_name = '%s / %s' % (category.parent_id.name, category.name)
            else:
                category.display_name = category.name