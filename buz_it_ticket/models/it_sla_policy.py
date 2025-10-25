# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class ItSlaPolicy(models.Model):
    _name = 'it.sla.policy'
    _description = 'IT SLA Policy'
    _order = 'category, priority'

    name = fields.Char('Policy Name', required=True)
    category = fields.Selection([
        ('issue', 'Issue/Repair'),
        ('access', 'Access Request'),
        ('purchase', 'Purchase Request'),
    ], string='Category', required=True)
    
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', required=True, default='1')
    
    subtype = fields.Char('Subtype', help='Optional subtype for more specific SLA rules')
    
    response_time_hours = fields.Float('Response Time (hours)', required=True, default=2.0,
                                       help='Maximum time to first respond to the ticket')
    
    resolve_time_hours = fields.Float('Resolve Time (hours)', required=True, default=24.0,
                                     help='Maximum time to resolve the ticket')
    
    active = fields.Boolean('Active', default=True)
    
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company,
                                 required=True)
    
    _sql_constraints = [
        ('unique_category_priority_subtype', 'unique(category, priority, subtype, company_id)',
         'SLA Policy must be unique per category, priority, subtype and company'),
    ]
    
    @api.model
    def get_sla_policy(self, category, priority, subtype=None):
        """
        Get the appropriate SLA policy for the given category, priority, and subtype
        """
        domain = [
            ('category', '=', category),
            ('priority', '=', priority),
            ('active', '=', True),
            ('company_id', 'in', [self.env.company.id, False]),
        ]
        
        if subtype:
            # First try to find a specific policy with subtype
            domain_with_subtype = domain + [('subtype', '=', subtype)]
            policy = self.search(domain_with_subtype, limit=1)
            if policy:
                return policy
        
        # Fallback to generic policy without subtype
        domain_without_subtype = domain + [('subtype', '=', False)]
        return self.search(domain_without_subtype, limit=1)