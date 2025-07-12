# -*- coding: utf-8 -*-

from datetime import timedelta
from odoo import models, fields, api
from datetime import timedelta


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
    project_count = fields.Integer(string='Projects', compute='_compute_project_count', store=True)
    total_contract_value = fields.Float(string='Total Contract Value', compute='_compute_contract_stats', store=True)
    completed_projects = fields.Integer(string='Completed Projects', compute='_compute_contract_stats', store=True)

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
            # Use a safer approach to get contract value - check if field exists
            if hasattr(projects, 'contract_amount'):
                record.total_contract_value = sum(projects.mapped('contract_amount'))
            else:
                # Fallback to project planned costs or budget if contract_amount doesn't exist
                record.total_contract_value = sum(projects.mapped('planned_amount') or [0])
            
            # More flexible stage checking for completed projects
            completed_stages = ['done', 'completed', 'finished', 'closed']
            record.completed_projects = len(projects.filtered(
                lambda p: p.stage_id and p.stage_id.name.lower() in completed_stages
            ))
    
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
        if self.env.context.get('default_is_subcontractor'):
            vals['is_subcontractor'] = True
        
        # Set supplier_rank if creating a subcontractor
        if vals.get('is_subcontractor') and 'supplier_rank' not in vals:
            vals['supplier_rank'] = 1
            
        return super(ResPartner, self).create(vals)

    def write(self, vals):
        """Override write to maintain consistency."""
        # If setting is_subcontractor to True, also set supplier_rank
        if vals.get('is_subcontractor'):
            for record in self:
                if record.supplier_rank == 0:
                    vals['supplier_rank'] = 1
                    break
            
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

    def action_remove_subcontractor_status(self):
        """Manual action to remove subcontractor status."""
        self.write({'is_subcontractor': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'{self.name} is no longer a subcontractor.',
                'type': 'info',
            }
        }

    def action_open_subcontractor_form(self):
        """Open the subcontractor-specific form view."""
        return {
            'name': 'Subcontractor',
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('job_costing_management.view_subcontractor_form').id,
            'target': 'current',
        }

    @api.model 
    def get_subcontractors_by_specialization(self, specialization_name):
        """Get all subcontractors with a specific specialization."""
        specialization = self.env['job.type'].search([('name', '=', specialization_name)], limit=1)
        if specialization:
            return self.search([
                ('is_subcontractor', '=', True),
                ('specialization_ids', 'in', specialization.ids)
            ])
        return self.browse()

    @api.model
    def get_available_subcontractors(self, project_id=None):
        """Get subcontractors available for assignment (not overloaded)."""
        # Check license expiry
        today = fields.Date.context_today(self)
        domain = [
            ('is_subcontractor', '=', True),
            '|',
            ('license_expiry', '=', False),
            ('license_expiry', '>', today)
        ]
        
        return self.search(domain)

    def get_performance_rating(self):
        """Calculate performance rating based on completed projects."""
        if self.project_count == 0:
            return 0
        completion_rate = self.completed_projects / self.project_count
        return min(5, max(1, int(completion_rate * 5) + 1))

    @api.model
    def send_license_expiry_reminders(self):
        """Cron job method to send license expiry reminders."""
        # Find subcontractors with licenses expiring in next 30 days
        expiry_date = fields.Date.context_today(self) + timedelta(days=30)
        expiring_licenses = self.search([
            ('is_subcontractor', '=', True),
            ('license_expiry', '!=', False),
            ('license_expiry', '<=', expiry_date)
        ])
        
        for subcontractor in expiring_licenses:
            # You can implement email notification here
            # For now, just log a message
            subcontractor.message_post(
                body=f"License expiry reminder: {subcontractor.trade_license} expires on {subcontractor.license_expiry}",
                subject="License Expiry Reminder"
            )
        
        return True

    @api.model
    def action_debug_subcontractors(self):
        """Debug method to check existing subcontractors."""
        subcontractors = self.search([('is_subcontractor', '=', True)])
        all_partners = self.search([])
        message = f"Found {len(subcontractors)} subcontractors out of {len(all_partners)} total partners:\n"
        for sc in subcontractors:
            message += f"- {sc.name} (ID: {sc.id}, is_subcontractor: {sc.is_subcontractor})\n"
        
        # Also check recent partners that might be subcontractors
        recent_partners = self.search([], order='create_date desc', limit=10)
        message += f"\nRecent 10 partners:\n"
        for partner in recent_partners:
            message += f"- {partner.name} (ID: {partner.id}, is_subcontractor: {partner.is_subcontractor}, supplier_rank: {partner.supplier_rank})\n"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Subcontractor Debug Info',
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }

    @api.model
    def action_fix_subcontractor_records(self):
        """Helper method to fix existing subcontractor records that might not be showing."""
        # Find partners that might be subcontractors but don't have the flag set
        partners_with_subcontractor_data = self.search([
            '|', '|', '|',
            ('trade_license', '!=', False),
            ('subcontractor_type', '!=', False),
            ('specialization_ids', '!=', False),
            ('contact_person', '!=', False)
        ])
        
        fixed_count = 0
        for partner in partners_with_subcontractor_data:
            if not partner.is_subcontractor:
                partner.write({
                    'is_subcontractor': True,
                    'supplier_rank': max(partner.supplier_rank, 1)
                })
                fixed_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Subcontractor Records Fixed',
                'message': f'Fixed {fixed_count} partner records to show as subcontractors.',
                'type': 'success',
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
