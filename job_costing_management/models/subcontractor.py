# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_subcontractor = fields.Boolean(string='Is Subcontractor', default=False)
    subcontractor_type = fields.Selection([
        ('individual', 'Individual'),
        ('company', 'Company')
    ], string='Subcontractor Type', default='company')
    
    # Subcontractor specific fields
    trade_license = fields.Char(string='Trade License')
    license_expiry = fields.Date(string='License Expiry Date')
    specialization_ids = fields.Many2many('job.type', string='Specializations')
    rating = fields.Selection([
        ('1', '⭐'),
        ('2', '⭐⭐'),
        ('3', '⭐⭐⭐'),
        ('4', '⭐⭐⭐⭐'),
        ('5', '⭐⭐⭐⭐⭐')
    ], string='Rating')
    
    # Contact details
    contact_person = fields.Char(string='Contact Person')
    emergency_contact = fields.Char(string='Emergency Contact')
    
    # Project relations
    project_ids = fields.Many2many('project.project', 'project_subcontractor_rel', 
                                  'partner_id', 'project_id', 
                                  string='Projects')
    
    # Statistics
    project_count = fields.Integer(string='Projects', compute='_compute_project_count')
    total_contract_value = fields.Float(string='Total Contract Value', compute='_compute_contract_stats')
    completed_projects = fields.Integer(string='Completed Projects', compute='_compute_contract_stats')

    @api.model
    def default_get(self, fields_list):
        """Override default_get to set subcontractor defaults when context indicates."""
        defaults = super(ResPartner, self).default_get(fields_list)
        
        # If we're in subcontractor context, set appropriate defaults
        if self.env.context.get('default_is_subcontractor'):
            defaults.update({
                'is_subcontractor': True,
                'supplier_rank': 1,
                'is_company': True,
                'subcontractor_type': 'company'
            })
        
        return defaults
    
    @api.depends('project_ids')
    def _compute_project_count(self):
        for record in self:
            record.project_count = len(record.project_ids)
    
    @api.depends('project_ids')
    def _compute_contract_stats(self):
        for record in self:
            projects = record.project_ids
            record.total_contract_value = sum(projects.mapped('contract_amount'))
            record.completed_projects = len(projects.filtered(lambda p: p.stage_id.name in ['Done', 'Completed']))
    
    def action_view_projects(self):
        return {
            'name': 'Projects',
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.project_ids.ids)],
        }

    @api.model
    def create(self, vals):
        """Override create to ensure subcontractor flag is set correctly."""
        # If we're creating from subcontractor context, ensure the flag is set
        if self.env.context.get('default_is_subcontractor') and 'is_subcontractor' not in vals:
            vals['is_subcontractor'] = True
        
        # Set supplier_rank if creating a subcontractor
        if vals.get('is_subcontractor') and 'supplier_rank' not in vals:
            vals['supplier_rank'] = 1
            
        return super(ResPartner, self).create(vals)

    def write(self, vals):
        """Override write to maintain consistency."""
        # If setting is_subcontractor to True, also set supplier_rank
        if vals.get('is_subcontractor') and self.supplier_rank == 0:
            vals['supplier_rank'] = 1
            
        return super(ResPartner, self).write(vals)

    def action_set_as_subcontractor(self):
        """Manual action to set partner as subcontractor."""
        self.write({
            'is_subcontractor': True,
            'supplier_rank': 1
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'{self.name} has been set as subcontractor.',
                'type': 'success',
            }
        }

    @api.model
    def action_debug_subcontractors(self):
        """Debug method to check existing subcontractors."""
        subcontractors = self.search([('is_subcontractor', '=', True)])
        message = f"Found {len(subcontractors)} subcontractors: {', '.join(subcontractors.mapped('name'))}"
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'info',
            }
        }


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dest_location_id = fields.Many2one('stock.location', string='Destination Location',
                                      help='Default destination location for material requisitions')


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    dest_location_id = fields.Many2one('stock.location', string='Department Location',
                                      help='Default destination location for department material requisitions')
