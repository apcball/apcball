# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class ItAccessTemplate(models.Model):
    _name = 'it.access.template'
    _description = 'IT Access Template'
    _order = 'name'

    name = fields.Char('Template Name', required=True)
    description = fields.Text('Description')
    
    department_id = fields.Many2one('hr.department', 'Department')
    
    line_ids = fields.One2many('it.access.template.line', 'template_id', 'Access Lines')
    
    active = fields.Boolean('Active', default=True)
    
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company,
                                 required=True)


class ItAccessTemplateLine(models.Model):
    _name = 'it.access.template.line'
    _description = 'IT Access Template Line'
    _order = 'access_type'

    template_id = fields.Many2one('it.access.template', 'Template', required=True, ondelete='cascade')
    
    access_type = fields.Selection([
        ('email', 'Email Account'),
        ('erp', 'ERP Access'),
        ('vpn', 'VPN Access'),
        ('drive', 'Drive/Storage'),
        ('shared_folder', 'Shared Folder'),
        ('software', 'Software License'),
        ('other', 'Other'),
    ], string='Access Type', required=True)
    
    name = fields.Char('Access Name', required=True, help='Specific name of the access (e.g., "Sales ERP Module")')
    
    access_payload = fields.Text('Access Details', help='JSON or text details about the access (groups, roles, modules, etc.)')
    
    notes = fields.Text('Notes')