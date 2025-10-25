# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, timedelta


class ItTicketSummaryWizard(models.TransientModel):
    _name = 'it.ticket.summary.wizard'
    _description = 'IT Ticket Summary Wizard'

    date_from = fields.Date('From Date', required=True, default=lambda self: fields.Date.today() - timedelta(days=30))
    date_to = fields.Date('To Date', required=True, default=lambda self: fields.Date.today())
    category = fields.Selection([
        ('all', 'All Categories'),
        ('issue', 'Issue/Repair'),
        ('access', 'Access Request'),
        ('purchase', 'Purchase Request'),
    ], string='Category', default='all', required=True)
    
    department_id = fields.Many2one('hr.department', 'Department')
    
    # Selection fields for report
    category_selection = fields.Selection([
        ('issue', 'Issue/Repair'),
        ('access', 'Access Request'),
        ('purchase', 'Purchase Request'),
    ], string='Category Selection', compute='_compute_selection_fields')
    
    priority_selection = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority Selection', compute='_compute_selection_fields')
    
    state_selection = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('in_progress', 'In Progress'),
        ('pending_info', 'Pending Info'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('waiting_manager', 'Waiting Manager'),
        ('approved', 'Approved'),
        ('implementing', 'Implementing'),
        ('rejected', 'Rejected'),
        ('waiting_it', 'Waiting IT'),
        ('po_created', 'PO Created'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ], string='State Selection', compute='_compute_selection_fields')
    
    @api.depends('category')
    def _compute_selection_fields(self):
        """Compute selection fields for report"""
        for wizard in self:
            # These are static selections, so we just set them
            wizard.category_selection = [
                ('issue', 'Issue/Repair'),
                ('access', 'Access Request'),
                ('purchase', 'Purchase Request'),
            ]
            wizard.priority_selection = [
                ('0', 'Low'),
                ('1', 'Normal'),
                ('2', 'High'),
                ('3', 'Urgent'),
            ]
            wizard.state_selection = [
                ('draft', 'Draft'),
                ('submitted', 'Submitted'),
                ('in_progress', 'In Progress'),
                ('pending_info', 'Pending Info'),
                ('resolved', 'Resolved'),
                ('closed', 'Closed'),
                ('waiting_manager', 'Waiting Manager'),
                ('approved', 'Approved'),
                ('implementing', 'Implementing'),
                ('rejected', 'Rejected'),
                ('waiting_it', 'Waiting IT'),
                ('po_created', 'PO Created'),
                ('received', 'Received'),
                ('cancelled', 'Cancelled'),
            ]

    def generate_report(self):
        """Generate the report data"""
        self.ensure_one()
        
        # Build domain for ticket search
        domain = [
            ('create_date', '>=', fields.Datetime.to_string(self.date_from)),
            ('create_date', '<=', fields.Datetime.to_string(self.date_to + timedelta(days=1))),
        ]
        
        if self.category != 'all':
            domain.append(('category', '=', self.category))
        
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        
        # Get tickets
        tickets = self.env['it.ticket'].search(domain)
        
        # Prepare ticket data
        ticket_data = []
        for ticket in tickets:
            # Calculate purchase line total
            purchase_line_total = 0
            if ticket.category == 'purchase':
                for line in ticket.purchase_line_ids:
                    purchase_line_total += line.quantity * line.estimated_cost
            
            ticket_data.append({
                'name': ticket.name,
                'category': ticket.category,
                'employee_name': ticket.employee_id.name,
                'department_name': ticket.department_id.name if ticket.department_id else None,
                'priority': ticket.priority,
                'state': ticket.state,
                'create_date': ticket.create_date.strftime('%Y-%m-%d'),
                'ttr_respond': '%.2f' % ticket.ttr_respond if ticket.ttr_respond else None,
                'ttr_resolve': '%.2f' % ticket.ttr_resolve if ticket.ttr_resolve else None,
                'sla_breached': ticket.sla_breached,
                'purchase_line_total': purchase_line_total,
            })
        
        # Calculate category statistics
        category_stats = []
        categories = [('issue', 'Issue/Repair'), ('access', 'Access Request'), ('purchase', 'Purchase Request')]
        
        for cat_code, cat_name in categories:
            cat_tickets = [t for t in ticket_data if t['category'] == cat_code]
            total = len(cat_tickets)
            open_count = len([t for t in cat_tickets if t['state'] in ['draft', 'submitted', 'waiting_manager', 'waiting_it']])
            in_progress = len([t for t in cat_tickets if t['state'] in ['in_progress', 'pending_info', 'approved', 'implementing', 'po_created']])
            closed = len([t for t in cat_tickets if t['state'] in ['resolved', 'closed', 'received']])
            sla_breached = len([t for t in cat_tickets if t['sla_breached']])
            
            # Calculate averages
            response_times = [float(t['ttr_respond']) for t in cat_tickets if t['ttr_respond']]
            resolution_times = [float(t['ttr_resolve']) for t in cat_tickets if t['ttr_resolve']]
            
            avg_response = sum(response_times) / len(response_times) if response_times else 0
            avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else 0
            
            category_stats.append({
                'name': cat_name,
                'total': total,
                'open': open_count,
                'in_progress': in_progress,
                'closed': closed,
                'sla_breached': sla_breached,
                'avg_response': '%.2f' % avg_response,
                'avg_resolution': '%.2f' % avg_resolution,
            })
        
        # Calculate department statistics
        department_stats = []
        departments = set(t['department_name'] for t in ticket_data if t['department_name'])
        departments.add(None)  # Include tickets without department
        
        for dept in departments:
            dept_tickets = [t for t in ticket_data if t['department_name'] == dept]
            total = len(dept_tickets)
            issue = len([t for t in dept_tickets if t['category'] == 'issue'])
            access = len([t for t in dept_tickets if t['category'] == 'access'])
            purchase = len([t for t in dept_tickets if t['category'] == 'purchase'])
            purchase_cost = sum(t['purchase_line_total'] for t in dept_tickets)
            
            department_stats.append({
                'name': dept,
                'total': total,
                'issue': issue,
                'access': access,
                'purchase': purchase,
                'purchase_cost': '%.2f' % purchase_cost,
            })
        
        # Sort departments by name (None goes last)
        department_stats.sort(key=lambda x: (x['name'] is None, x['name']))
        
        # Prepare data for report
        data = {
            'form': {
                'date_from': self.date_from.strftime('%Y-%m-%d'),
                'date_to': self.date_to.strftime('%Y-%m-%d'),
                'category': self.category,
                'category_selection': dict(self.category_selection),
                'priority_selection': dict(self.priority_selection),
                'state_selection': dict(self.state_selection),
            },
            'tickets': ticket_data,
            'category_stats': category_stats,
            'department_stats': department_stats,
        }
        
        # Return the report action properly
        return self.env.ref('buz_it_ticket.action_report_it_ticket_summary').report_action(self, data=data)