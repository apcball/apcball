from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError, AccessError, MissingError
from datetime import date
import logging

_logger = logging.getLogger(__name__)

class SalesTarget(models.Model):
    _name = 'sales.target'
    _description = 'Sales Target'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'
    _rec_name = 'display_name'
    _check_company_auto = True

    # Multi-Company
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    # Basic Information
    name = fields.Char(string='Description', required=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    user_id = fields.Many2one('res.users', string='Salesperson', check_company=True)
    team_ids = fields.Many2many('crm.team', string='Sales Teams')
    team_member_ids = fields.Many2many('res.users', string='Team Members', compute='_compute_team_members')
    responsible_id = fields.Many2one('res.users', string='Responsible', compute='_compute_responsible', store=True)
    
    # Target Configuration
    target_amount = fields.Monetary(string='Target Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id', string='Currency', readonly=True)
    target_point = fields.Selection([
        ('sale_order', 'Sale Order Confirm'),
        ('delivery', 'Delivery Confirmed'),
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
    achieved_amount = fields.Monetary(string='Achieved Amount', compute='_compute_achieved_amount', currency_field='currency_id')
    percent_achieved = fields.Float(string='Achievement %', compute='_compute_percent_achieved')
    
    # Theoretical Achievement (non-stored because it depends on date.today())
    theoretical_amount = fields.Monetary(string='Theoretical Amount', compute='_compute_theoretical_achievement', store=False, currency_field='currency_id')
    theoretical_percent = fields.Float(string='Theoretical %', compute='_compute_theoretical_achievement', store=False)
    theoretical_status = fields.Selection([
        ('above', 'Above Target'),
        ('on_track', 'On Track'),
        ('below', 'Below Target')
    ], string='Theoretical Status', compute='_compute_theoretical_achievement', store=False, default='below')
    
    # Notification Settings
    email_notification = fields.Boolean(string='Send Email Notification', default=True)
    email_template_id = fields.Many2one('mail.template', string='Email Template')
    last_notification_date = fields.Date(string='Last Notification Date')
    
    # Counters
    sale_order_count = fields.Integer(string='Sale Orders', compute='_compute_counters')
    sale_order_line_count = fields.Integer(string='Sale Order Lines', compute='_compute_counters')
    invoice_count = fields.Integer(string='Invoices', compute='_compute_counters')
    invoice_line_count = fields.Integer(string='Invoice Lines', compute='_compute_counters')
    total_ordered_qty = fields.Float(string='Total Ordered Qty', compute='_compute_counters')
    total_delivered_qty = fields.Float(string='Total Delivered Qty', compute='_compute_counters')
    delivery_order_count = fields.Integer(string='Delivery Orders', compute='_compute_counters')
    
    # Additional Information
    note = fields.Text(string='Notes', help='Additional notes and comments about this sales target')

    _sql_constraints = [
        ('check_target_amount_positive', 'CHECK(target_amount > 0)', 'Target amount must be positive.'),
        ('check_dates_consistency', 'CHECK(date_start <= date_end)', 'Start date must be before end date.'),
    ]

    @api.depends('name', 'user_id', 'team_ids', 'date_start', 'date_end')
    def _compute_display_name(self):
        for record in self:
            parts = []
            if record.name:
                parts.append(record.name)
            if record.user_id:
                parts.append(f"({record.user_id.name})")
            elif record.team_ids:
                parts.append(f"({', '.join(record.team_ids.mapped('name'))})")
            if record.date_start and record.date_end:
                parts.append(f"[{record.date_start} - {record.date_end}]")
            record.display_name = ' '.join(parts) if parts else 'Sales Target'

    @api.depends('user_id', 'team_ids')
    def _compute_responsible(self):
        for record in self:
            if record.user_id:
                record.responsible_id = record.user_id
            elif record.team_ids:
                responsible = False
                for team in record.team_ids:
                    if team.user_id:
                        responsible = team.user_id
                        break
                record.responsible_id = responsible or self.env.user
            else:
                record.responsible_id = self.env.user

    @api.depends('team_ids')
    def _compute_team_members(self):
        for record in self:
            members = record.team_ids.mapped('member_ids') | record.team_ids.mapped('user_id')
            record.team_member_ids = members

    @api.depends('target_point', 'date_start', 'date_end', 'user_id', 'team_ids')
    def _compute_achieved_amount(self):
        for record in self:
            if not record.date_start or not record.date_end:
                record.achieved_amount = 0.0
                continue
                
            try:
                if record.target_point == 'sale_order':
                    domain = record._get_sale_order_domain()
                    sale_orders = self.env['sale.order'].search(domain)
                    _logger.debug(f"Sales Target {record.name}: Found {len(sale_orders)} sale orders")
                    record.achieved_amount = sum(sale_orders.mapped('amount_untaxed'))
                    
                elif record.target_point == 'delivery':
                    domain = record._get_sale_order_domain()
                    sale_orders = self.env['sale.order'].search(domain)
                    delivered_amount = 0.0
                    done_pickings = sale_orders.mapped('picking_ids').filtered(
                        lambda p: p.state == 'done'
                    )
                    for picking in done_pickings:
                        for move in picking.move_ids.filtered(
                            lambda m: m.state == 'done' and m.sale_line_id
                        ):
                            sol = move.sale_line_id
                            if sol.product_uom_qty > 0 and move.quantity > 0:
                                unit_price = sol.price_subtotal / sol.product_uom_qty
                                if picking.picking_type_code == 'outgoing':
                                    delivered_amount += move.quantity * unit_price
                                elif picking.picking_type_code == 'incoming':
                                    delivered_amount -= move.quantity * unit_price
                    record.achieved_amount = delivered_amount
                    
                elif record.target_point in ['invoice_validate', 'invoice_paid']:
                    domain = record._get_invoice_domain()
                    invoices = self.env['account.move'].search(domain)
                    _logger.debug(f"Sales Target {record.name}: Found {len(invoices)} invoices")
                    record.achieved_amount = sum(invoices.mapped('amount_total_signed'))
                    
                else:
                    record.achieved_amount = 0.0
                    
            except (AccessError, MissingError) as e:
                _logger.warning(f"Access error computing achieved amount for target {record.id}: {e}")
                record.achieved_amount = 0.0

    @api.depends('achieved_amount', 'target_amount')
    def _compute_percent_achieved(self):
        for record in self:
            if record.target_amount:
                record.percent_achieved = record.achieved_amount / record.target_amount
            else:
                record.percent_achieved = 0.0

    @api.depends('target_amount', 'date_start', 'date_end', 'achieved_amount')
    def _compute_theoretical_achievement(self):
        today = date.today()
        for record in self:
            if not record.date_start or not record.date_end or not record.target_amount:
                record.theoretical_amount = 0.0
                record.theoretical_percent = 0.0
                record.theoretical_status = 'below'
                continue
                
            # Calculate theoretical achievement based on time elapsed
            total_days = (record.date_end - record.date_start).days + 1
            if today <= record.date_start:
                elapsed_days = 0
            elif today >= record.date_end:
                elapsed_days = total_days
            else:
                elapsed_days = (today - record.date_start).days + 1
                
            if total_days > 0:
                time_ratio = elapsed_days / total_days
                record.theoretical_amount = record.target_amount * time_ratio
                record.theoretical_percent = time_ratio
                
                # Determine status
                if record.achieved_amount >= record.target_amount:
                    record.theoretical_status = 'above'
                elif record.achieved_amount >= record.theoretical_amount:
                    record.theoretical_status = 'on_track'
                else:
                    record.theoretical_status = 'below'
            else:
                record.theoretical_amount = 0.0
                record.theoretical_percent = 0.0
                record.theoretical_status = 'below'

    @api.depends('target_point', 'date_start', 'date_end', 'user_id', 'team_ids')
    def _compute_counters(self):
        for record in self:
            if not record.date_start or not record.date_end:
                record.sale_order_count = 0
                record.sale_order_line_count = 0
                record.invoice_count = 0
                record.invoice_line_count = 0
                record.total_ordered_qty = 0.0
                record.total_delivered_qty = 0.0
                record.delivery_order_count = 0
                continue
                
            try:
                # Sale orders
                sale_domain = record._get_sale_order_domain()
                sale_orders = self.env['sale.order'].search(sale_domain)
                record.sale_order_count = len(sale_orders)
                
                # Delivery orders
                if sale_orders:
                    done_pickings = sale_orders.mapped('picking_ids').filtered(
                        lambda p: p.state == 'done'
                    )
                    record.delivery_order_count = len(done_pickings)
                else:
                    record.delivery_order_count = 0
                
                # Sale order lines / quantities
                if sale_orders:
                    sale_lines = self.env['sale.order.line'].search([('order_id', 'in', sale_orders.ids)])
                    record.sale_order_line_count = len(sale_lines)
                    record.total_ordered_qty = sum(sale_lines.mapped('product_uom_qty'))
                    done_pickings = sale_orders.mapped('picking_ids').filtered(
                        lambda p: p.state == 'done'
                    )
                    out_moves = done_pickings.filtered(
                        lambda p: p.picking_type_code == 'outgoing'
                    ).mapped('move_ids').filtered(lambda m: m.state == 'done')
                    in_moves = done_pickings.filtered(
                        lambda p: p.picking_type_code == 'incoming'
                    ).mapped('move_ids').filtered(lambda m: m.state == 'done')
                    record.total_delivered_qty = (
                        sum(out_moves.mapped('quantity'))
                        - sum(in_moves.mapped('quantity'))
                    )
                else:
                    record.sale_order_line_count = 0
                    record.total_ordered_qty = 0.0
                    record.total_delivered_qty = 0.0
                    
                # Invoices
                invoice_domain = record._get_invoice_domain()
                invoices = self.env['account.move'].search(invoice_domain)
                record.invoice_count = len(invoices)
                
                # Invoice lines
                if invoices:
                    invoice_lines = self.env['account.move.line'].search([
                        ('move_id', 'in', invoices.ids),
                        ('display_type', 'not in', ['line_section', 'line_note'])
                    ])
                    record.invoice_line_count = len(invoice_lines)
                else:
                    record.invoice_line_count = 0
                    
            except (AccessError, MissingError) as e:
                _logger.warning(f"Access error computing counters for target {record.id}: {e}")
                record.sale_order_count = 0
                record.sale_order_line_count = 0
                record.invoice_count = 0
                record.invoice_line_count = 0
                record.total_ordered_qty = 0.0
                record.total_delivered_qty = 0.0
                record.delivery_order_count = 0

    def _get_sale_order_domain(self):
        """Get domain for sale orders based on target configuration."""
        domain = [
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', self.date_start),
            ('date_order', '<=', self.date_end),
            ('company_id', '=', self.company_id.id),
        ]
        
        if self.user_id:
            domain.append(('user_id', '=', self.user_id.id))
        elif self.team_ids:
            domain.append(('team_id', 'in', self.team_ids.ids))
            
        return domain

    def _get_invoice_domain(self):
        """Get domain for invoices based on target configuration."""
        base_domain = [
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', 'not in', ['draft', 'cancel']),
            ('company_id', '=', self.company_id.id),
        ]
        
        # Date field depends on target point
        if self.target_point == 'invoice_validate':
            base_domain.extend([
                ('invoice_date', '>=', self.date_start),
                ('invoice_date', '<=', self.date_end)
            ])
        elif self.target_point == 'invoice_paid':
            base_domain.extend([
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['paid', 'in_payment']),
                ('invoice_date', '>=', self.date_start),
                ('invoice_date', '<=', self.date_end)
            ])
        
        if self.user_id:
            base_domain.append(('invoice_user_id', '=', self.user_id.id))
        elif self.team_ids:
            base_domain.append(('team_id', 'in', self.team_ids.ids))
            
        return base_domain

    # Action Methods
    def action_view_sale_orders(self):
        """View related sale orders."""
        domain = self._get_sale_order_domain()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Orders'),
            'res_model': 'sale.order',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'default_user_id': self.user_id.id if self.user_id else False,
                'default_team_id': self.team_ids[:1].id if self.team_ids else False,
            }
        }

    def action_view_sale_order_lines(self):
        """View related sale order lines."""
        sale_domain = self._get_sale_order_domain()
        sale_orders = self.env['sale.order'].search(sale_domain)
        
        domain = [('order_id', 'in', sale_orders.ids)]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order Lines'),
            'res_model': 'sale.order.line',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {}
        }

    def action_view_invoices(self):
        """View related invoices."""
        domain = self._get_invoice_domain()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'default_move_type': 'out_invoice',
                'default_invoice_user_id': self.user_id.id if self.user_id else False,
                'default_team_id': self.team_ids[:1].id if self.team_ids else False,
            }
        }

    def action_view_invoice_lines(self):
        """View related invoice lines."""
        invoice_domain = self._get_invoice_domain()
        invoices = self.env['account.move'].search(invoice_domain)
        
        domain = [
            ('move_id', 'in', invoices.ids),
            ('display_type', 'not in', ['line_section', 'line_note'])
        ]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice Lines'),
            'res_model': 'account.move.line',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {}
        }

    def action_view_delivery_orders(self):
        """View related delivery orders (done only for delivery target point)."""
        domain = self._get_sale_order_domain()
        sale_orders = self.env['sale.order'].search(domain)
        pickings = sale_orders.mapped('picking_ids')
        if self.target_point == 'delivery':
            pickings = pickings.filtered(lambda p: p.state == 'done')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery Orders'),
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', pickings.ids)] if pickings else [('id', '=', False)],
            'context': {}
        }

    def action_confirm(self):
        """Confirm the sales target."""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft targets can be confirmed.'))
            record.state = 'confirmed'
            record.message_post(body=_('Sales target confirmed.'))

    def action_close(self):
        """Close the sales target."""
        for record in self:
            if record.state not in ['draft', 'confirmed']:
                raise UserError(_('Only draft or confirmed targets can be closed.'))
            record.state = 'closed'
            record.message_post(body=_('Sales target closed.'))

    def action_reset_to_draft(self):
        """Reset to draft state."""
        for record in self:
            if record.state != 'confirmed':
                raise UserError(_('Only confirmed targets can be reset to draft.'))
            record.state = 'draft'
            record.message_post(body=_('Sales target reset to draft.'))

    def action_send_mail(self):
        """Send achievement notification via button click."""
        for record in self:
            record.send_achievement_notification()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Achievement notification email has been sent.'),
            }
        }

    def action_recompute_achievement(self):
        """Manually recompute achievement amounts."""
        for record in self:
            record._compute_achieved_amount()
            record._compute_percent_achieved()
            record._compute_theoretical_achievement()
            record._compute_counters()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Achievement amounts have been recomputed.'),
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
                raise ValidationError(_('Target amount must be positive.'))

    @api.constrains('user_id', 'team_ids')
    def _check_user_or_team(self):
        for record in self:
            if record.user_id and record.team_ids:
                raise ValidationError(_('Cannot set both Salesperson and Sales Team. Choose one.'))
            if not record.user_id and not record.team_ids:
                raise ValidationError(_('Either Salesperson or Sales Team must be specified.'))

    # Notification Methods
    def send_achievement_notification(self):
        """Send achievement notification email."""
        for record in self:
            if not record.email_notification or not record.responsible_id:
                continue
                
            template = record.email_template_id
            if not template:
                template = self.env.ref('sales_target_custom.email_template_target_manual', raise_if_not_found=False)
                
            if template:
                try:
                    template.send_mail(record.id, force_send=True)
                    record.last_notification_date = date.today()
                    _logger.info(f"Achievement notification sent for target {record.id}")
                except Exception as e:
                    _logger.error(f"Failed to send achievement notification: {e}")

    @api.model
    def cron_check_achievements(self):
        """Cron job to check achievements and send notifications."""
        targets = self.search([
            ('state', '=', 'confirmed'),
            ('email_notification', '=', True),
            ('date_end', '>=', date.today())
        ])
        today = date.today()
        for target in targets:
            target._compute_achieved_amount()
            target._compute_percent_achieved()
            target._compute_theoretical_achievement()
            target._compute_counters()
            already_notified_today = (
                target.last_notification_date
                and target.last_notification_date == today
            )
            if already_notified_today:
                continue
            if target.percent_achieved >= 100 or target.theoretical_status == 'below':
                target.send_achievement_notification()
