# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date
import calendar
import logging

_logger = logging.getLogger(__name__)

class SalesTarget(models.Model):
    _name = 'sales.target'
    _description = 'Sales Target'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'
    _rec_name = 'display_name'

    # Basic Information
    name = fields.Char(string='Description', required=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    user_id = fields.Many2one('res.users', string='Salesperson')
    team_id = fields.Many2one('crm.team', string='Sales Team')
    responsible_id = fields.Many2one('res.users', string='Responsible', compute='_compute_responsible', store=True)
    
    # Target Configuration
    target_amount = fields.Monetary(string='Target Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id)
    target_point = fields.Selection([
        ('sale_order', 'Sale Order Confirm'),
        ('invoice_validate', 'Invoice Validation'),
        ('invoice_paid', 'Invoice Paid')
    ], string='Target Point', required=True, default='sale_order')
    
    # Date Range
    date_start = fields.Date(string='Start Date', required=True)
    date_end = fields.Date(string='End Date', required=True)
    
    # State Management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('closed', 'Closed')
    ], string='State', default='draft', tracking=True)
    
    # Achievement Calculations
    achieved_amount = fields.Monetary(string='Achieved Amount', compute='_compute_achieved_amount', store=True, currency_field='currency_id')
    percent_achieved = fields.Float(string='Achievement %', compute='_compute_percent_achieved', store=True)
    
    # Theoretical Achievement
    theoretical_amount = fields.Monetary(string='Theoretical Amount', compute='_compute_theoretical_achievement', store=True, currency_field='currency_id')
    theoretical_percent = fields.Float(string='Theoretical %', compute='_compute_theoretical_achievement', store=True)
    theoretical_status = fields.Selection([
        ('above', 'Above Target'),
        ('below', 'Below Target'),
        ('completed', 'Completed')
    ], string='Theoretical Status', compute='_compute_theoretical_achievement', store=True)
    
    # Additional Information
    note = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    # Invoice specific fields for additional tracking
    invoiced_amount = fields.Monetary(string='Invoiced Amount', compute='_compute_invoice_amounts', store=True, currency_field='currency_id')
    invoice_percent = fields.Float(string='Invoice %', compute='_compute_invoice_amounts', store=True)
    
    # Related lines for display
    sale_order_line_ids = fields.One2many('sale.order.line', compute='_compute_related_lines', string='Sale Order Lines')
    invoice_line_ids = fields.One2many('account.move.line', compute='_compute_related_lines', string='Invoice Lines')

    # Compute Methods
    @api.depends('name', 'user_id', 'team_id', 'date_start', 'date_end')
    def _compute_display_name(self):
        for record in self:
            parts = []
            if record.name:
                parts.append(record.name)
            if record.user_id:
                parts.append(record.user_id.name)
            elif record.team_id:
                parts.append(record.team_id.name)
            if record.date_start and record.date_end:
                parts.append(f"{record.date_start} - {record.date_end}")
            record.display_name = ' | '.join(parts) if parts else 'New Target'

    @api.depends('user_id', 'team_id')
    def _compute_responsible(self):
        for record in self:
            if record.user_id:
                record.responsible_id = record.user_id
            elif record.team_id and record.team_id.user_id:
                record.responsible_id = record.team_id.user_id
            else:
                record.responsible_id = self.env.user

    @api.depends('target_point', 'date_start', 'date_end', 'user_id', 'team_id', 'currency_id')
    def _compute_achieved_amount(self):
        for record in self:
            achieved = 0.0
            if record.target_point == 'sale_order':
                # Calculate from confirmed sale orders
                domain = record._get_sale_order_domain()
                orders = record.env['sale.order'].search(domain)
                achieved = sum(orders.mapped('amount_total'))
            elif record.target_point == 'invoice_validate':
                # Calculate from validated invoices
                domain = record._get_invoice_domain()
                invoices = record.env['account.move'].search(domain)
                achieved = sum(invoices.filtered(lambda inv: inv.state == 'posted').mapped('amount_total'))
            elif record.target_point == 'invoice_paid':
                # Calculate from paid invoices
                domain = record._get_invoice_domain()
                invoices = record.env['account.move'].search(domain)
                achieved = sum(invoices.filtered(lambda inv: inv.payment_state in ['paid', 'in_payment']).mapped('amount_total'))
            record.achieved_amount = achieved

    @api.depends('achieved_amount', 'target_amount')
    def _compute_percent_achieved(self):
        for record in self:
            if record.target_amount:
                # Store as decimal (0.49 = 49%) for percentage widget
                record.percent_achieved = record.achieved_amount / record.target_amount
            else:
                record.percent_achieved = 0.0

    @api.depends('date_start', 'date_end', 'target_amount')
    def _compute_theoretical_achievement(self):
        for record in self:
            today = date.today()
            
            # Check if current date is within target period
            if record.date_start and record.date_end:
                if record.date_start <= today <= record.date_end:
                    # Calculate theoretical achievement
                    total_days = (record.date_end - record.date_start).days + 1
                    current_day = (today - record.date_start).days + 1
                    
                    if total_days > 0:
                        theoretical_amount = (record.target_amount / total_days) * current_day
                        record.theoretical_amount = theoretical_amount
                        
                        if record.target_amount:
                            # Store as decimal (0.10 = 10%) for percentage widget
                            record.theoretical_percent = theoretical_amount / record.target_amount
                        else:
                            record.theoretical_percent = 0.0
                        
                        # Determine theoretical status
                        if record.achieved_amount > theoretical_amount:
                            record.theoretical_status = 'above'
                        elif record.achieved_amount < theoretical_amount:
                            record.theoretical_status = 'below'
                        else:
                            record.theoretical_status = 'completed'
                    else:
                        record.theoretical_amount = 0.0
                        record.theoretical_percent = 0.0
                        record.theoretical_status = 'completed'
                else:
                    # Outside target period
                    record.theoretical_amount = record.target_amount
                    record.theoretical_percent = 1.0  # 100% as decimal
                    record.theoretical_status = 'completed'
            else:
                record.theoretical_amount = 0.0
                record.theoretical_percent = 0.0
                record.theoretical_status = 'completed'

    @api.depends('target_point', 'date_start', 'date_end', 'user_id', 'team_id', 'currency_id')
    def _compute_invoice_amounts(self):
        for record in self:
            invoiced = 0.0
            if record.target_point in ['invoice_validate', 'invoice_paid']:
                domain = record._get_invoice_domain()
                invoices = record.env['account.move'].search(domain)
                invoiced = sum(invoices.mapped('amount_total'))
            
            record.invoiced_amount = invoiced
            if record.target_amount:
                record.invoice_percent = invoiced / record.target_amount
            else:
                record.invoice_percent = 0.0

    @api.depends('target_point', 'date_start', 'date_end', 'user_id', 'team_id')
    def _compute_related_lines(self):
        for record in self:
            if record.target_point == 'sale_order':
                domain = record._get_sale_order_domain()
                try:
                    orders = record.env['sale.order'].search(domain)
                    sale_lines = orders.mapped('order_line')
                    record.sale_order_line_ids = sale_lines.ids
                except:
                    record.sale_order_line_ids = []
                    
                record.invoice_line_ids = []
            elif record.target_point in ['invoice_validate', 'invoice_paid']:
                domain = record._get_invoice_domain()
                try:
                    invoices = record.env['account.move'].search(domain)
                    invoice_lines = invoices.mapped('invoice_line_ids')
                    record.invoice_line_ids = invoice_lines.ids
                except:
                    record.invoice_line_ids = []
                    
                record.sale_order_line_ids = []
            else:
                record.sale_order_line_ids = []
                record.invoice_line_ids = []

    # Action methods for viewing related records
    def action_view_sale_orders(self):
        """Open sale orders matching target criteria"""
        domain = self._get_sale_order_domain()
        return {
            'name': _('Sale Orders - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'default_user_id': self.user_id.id if self.user_id else False,
                'default_team_id': self.team_id.id if self.team_id else False,
            },
            'target': 'current',
        }

    def action_view_sale_order_lines(self):
        """Open sale order lines matching target criteria"""
        domain = self._get_sale_order_domain()
        # Get order lines from matching orders
        orders = self.env['sale.order'].search(domain)
        line_ids = orders.mapped('order_line').ids
        
        return {
            'name': _('Sale Order Lines - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.line',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', line_ids)],
            'context': {
                'group_by': 'order_id',
            },
            'target': 'current',
        }

    def action_view_invoices(self):
        """Open invoices matching target criteria"""
        domain = self._get_invoice_domain()
        return {
            'name': _('Invoices - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'default_invoice_user_id': self.user_id.id if self.user_id else False,
                'default_team_id': self.team_id.id if self.team_id else False,
            },
            'target': 'current',
        }

    def action_view_invoice_lines(self):
        """Open invoice lines matching target criteria"""
        domain = self._get_invoice_domain()
        # Get invoice lines from matching invoices
        invoices = self.env['account.move'].search(domain)
        line_ids = invoices.mapped('invoice_line_ids').ids
        
        return {
            'name': _('Invoice Lines - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', line_ids)],
            'context': {
                'group_by': 'move_id',
            },
            'target': 'current',
        }

    def _get_sale_order_domain(self):
        """Get domain for sale orders based on target criteria"""
        domain = [
            ('date_order', '>=', self.date_start),
            ('date_order', '<=', self.date_end),
            ('state', 'in', ['sale', 'done']),  # Confirmed orders only
        ]
        
        # Add user/team filter
        if self.user_id:
            domain.append(('user_id', '=', self.user_id.id))
        elif self.team_id:
            domain.append(('team_id', '=', self.team_id.id))
        
        # Add currency filter if needed
        if self.currency_id:
            domain.append(('currency_id', '=', self.currency_id.id))
        
        return domain

    def _get_invoice_domain(self):
        """Get domain for invoices based on target criteria"""
        domain = [
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '!=', 'draft'),
        ]
        
        # Date filter based on target point
        if self.target_point == 'invoice_validate':
            # Use invoice date for validation point
            domain.extend([
                ('invoice_date', '>=', self.date_start),
                ('invoice_date', '<=', self.date_end),
                ('state', '!=', 'cancel'),
            ])
        elif self.target_point == 'invoice_paid':
            # Use payment date for paid point - need to check payment reconciliation
            domain.extend([
                ('invoice_date', '>=', self.date_start),
                ('invoice_date', '<=', self.date_end),
                ('payment_state', 'in', ['paid', 'in_payment']),
            ])
        
        # Add user/team filter
        if self.user_id:
            domain.append(('invoice_user_id', '=', self.user_id.id))
        elif self.team_id:
            domain.append(('team_id', '=', self.team_id.id))
        
        # Add currency filter if needed
        if self.currency_id:
            domain.append(('currency_id', '=', self.currency_id.id))
        
        return domain

    # State Management Actions
    def action_confirm(self):
        self.write({'state': 'confirmed'})
        self._send_notification_email('confirm')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Target has been confirmed successfully.'),
                'type': 'success',
            }
        }

    def action_close(self):
        self.write({'state': 'closed'})
        self._send_notification_email('close')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Target has been closed successfully.'),
                'type': 'success',
            }
        }

    def action_draft(self):
        self.write({'state': 'draft'})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Target has been reset to draft.'),
                'type': 'info',
            }
        }

    def action_send_mail(self):
        self._send_notification_email('manual')

    def _send_notification_email(self, action_type):
        """Send email notification based on action type"""
        if not self:
            return
        
        template_mapping = {
            'confirm': 'sales_target_custom.email_template_target_confirmed',
            'close': 'sales_target_custom.email_template_target_closed',
            'manual': 'sales_target_custom.email_template_target_manual',
        }
        
        template_id = template_mapping.get(action_type)
        if not template_id:
            return
        
        try:
            template = self.env.ref(template_id)
            if template:
                for record in self:
                    # Send to responsible user
                    if record.responsible_id and record.responsible_id.email:
                        template.send_mail(record.id, force_send=True)
        except Exception as e:
            # Log error but don't stop the process
            _logger.warning(f"Failed to send email notification: {str(e)}")

    def action_recompute_achievements(self):
        """Recompute all achievement calculations for this record"""
        for record in self:
            # Force recompute of all computed fields
            record._compute_achieved_amount()
            record._compute_percent_achieved()
            record._compute_theoretical_achievement()
            record._compute_invoice_amounts()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Achievement calculations have been recomputed successfully.'),
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def recompute_all_targets(self):
        """Recompute all targets in the system - use carefully"""
        all_targets = self.search([])
        for target in all_targets:
            target.action_recompute_achievements()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('All %d target calculations have been recomputed successfully.') % len(all_targets),
                'type': 'success',
                'sticky': True,
            }
        }

    # Validation Methods
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_end:
                if record.date_start > record.date_end:
                    raise ValidationError(_('Start date must be before end date.'))

    @api.constrains('target_amount')
    def _check_target_amount(self):
        for record in self:
            if record.target_amount <= 0:
                raise ValidationError(_('Target amount must be greater than zero.'))

    @api.constrains('user_id', 'team_id', 'date_start', 'date_end', 'target_point')
    def _check_duplicate_targets(self):
        for record in self:
            domain = [
                ('id', '!=', record.id),
                ('date_start', '<=', record.date_end),
                ('date_end', '>=', record.date_start),
                ('target_point', '=', record.target_point),
                ('state', '!=', 'closed'),
            ]
            
            if record.user_id:
                domain.append(('user_id', '=', record.user_id.id))
            elif record.team_id:
                domain.append(('team_id', '=', record.team_id.id))
            
            existing = self.search(domain)
            if existing:
                raise ValidationError(_(
                    'A target with overlapping dates already exists for this user/team and target point.'
                ))
