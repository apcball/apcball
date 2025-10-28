from odoo import models, fields, api


class ITSLAPolicy(models.Model):
    _name = 'it.sla.policy'
    _description = 'IT SLA Policy'

    name = fields.Char('Policy Name', required=True)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'), 
        ('2', 'High'),
        ('3', 'Urgent')
    ], string='Priority Level', required=True)
    resolution_hours = fields.Float('Resolution Time (Hours)', required=True)
    warning_hours = fields.Float('Warning Time (Hours)', required=True)
    active = fields.Boolean(default=True)


class ITCategory(models.Model):
    _name = 'it.category'
    _description = 'IT Category'

    name = fields.Char('Category Name', required=True)
    description = fields.Text('Description')
    active = fields.Boolean(default=True)