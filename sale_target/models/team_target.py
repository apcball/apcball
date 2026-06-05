from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class SaleTeamTarget(models.Model):
    _name = 'sale.team.target'
    _description = 'Team Target'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'
    _rec_name = 'display_name'

    name = fields.Char(string='Description', required=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    team_ids = fields.Many2many('crm.team', string='Sales Teams', required=True)
    responsible_id = fields.Many2one('res.users', string='Responsible', compute='_compute_responsible', store=True)

    target_amount = fields.Monetary(string='Target Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id)
    target_point = fields.Selection([
        ('sale_order', 'Sale Order Confirm'),
        ('invoice_validate', 'Invoice Validation'),
        ('invoice_paid', 'Invoice Paid'),
    ], string='Target Point', required=True, default='sale_order')

    date_start = fields.Date(string='Start Date', required=True)
    date_end = fields.Date(string='End Date', required=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('closed', 'Closed'),
    ], string='State', default='draft', tracking=True)

    achieved_amount = fields.Monetary(string='Achieved Amount', compute='_compute_achieved_amount', store=True, currency_field='currency_id')
    percent_achieved = fields.Float(string='Achievement %', compute='_compute_percent_achieved', store=True)

    theoretical_amount = fields.Monetary(string='Theoretical Amount', compute='_compute_theoretical_achievement', store=True, currency_field='currency_id')
    theoretical_percent = fields.Float(string='Theoretical %', compute='_compute_theoretical_achievement', store=True)
    theoretical_status = fields.Selection([
        ('above', 'Above Target'),
        ('on_track', 'On Track'),
        ('below', 'Below Target'),
        ('completed', 'Completed'),
    ], string='Theoretical Status', compute='_compute_theoretical_achievement', store=True)

    invoiced_amount = fields.Monetary(string='Invoiced Amount', compute='_compute_invoice_amounts', store=True, currency_field='currency_id')
    invoice_percent = fields.Float(string='Invoice %', compute='_compute_invoice_amounts', store=True)

    note = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    sale_order_line_ids = fields.One2many('sale.order.line', compute='_compute_related_lines', string='Sale Order Lines')
    invoice_line_ids = fields.One2many('account.move.line', compute='_compute_related_lines', string='Invoice Lines')

    sale_order_count = fields.Integer(string='Sale Orders', compute='_compute_counters')
    sale_order_line_count = fields.Integer(string='Sale Order Lines', compute='_compute_counters')
    invoice_count = fields.Integer(string='Invoices', compute='_compute_counters')
    invoice_line_count = fields.Integer(string='Invoice Lines', compute='_compute_counters')

    email_notification = fields.Boolean(string='Send Email Notification', default=True)

    @api.depends('name', 'team_ids', 'date_start', 'date_end')
    def _compute_display_name(self):
        for record in self:
            parts = []
            if record.name:
                parts.append(record.name)
            if record.team_ids:
                parts.append(', '.join(record.team_ids.mapped('name')))
            if record.date_start and record.date_end:
                parts.append(f"{record.date_start} - {record.date_end}")
            record.display_name = ' | '.join(parts) if parts else 'New Target'

    @api.depends('team_ids')
    def _compute_responsible(self):
        for record in self:
            responsible = False
            for team in record.team_ids:
                if team.user_id:
                    responsible = team.user_id
                    break
            record.responsible_id = responsible or self.env.user

    @api.depends('target_point', 'date_start', 'date_end', 'team_ids', 'currency_id')
    def _compute_achieved_amount(self):
        for record in self:
            achieved = 0.0
            if record.target_point == 'sale_order':
                domain = record._get_sale_order_domain()
                orders = record.env['sale.order'].search(domain)
                achieved = sum(orders.mapped('amount_total'))
            elif record.target_point in ('invoice_validate', 'invoice_paid'):
                domain = record._get_invoice_domain()
                invoices = record.env['account.move'].search(domain)
                achieved = sum(invoices.mapped('amount_total'))
            record.achieved_amount = achieved

    @api.depends('achieved_amount', 'target_amount')
    def _compute_percent_achieved(self):
        for record in self:
            record.percent_achieved = record.achieved_amount / record.target_amount if record.target_amount else 0.0

    @api.depends('date_start', 'date_end', 'target_amount', 'achieved_amount')
    def _compute_theoretical_achievement(self):
        today = date.today()
        for record in self:
            if record.date_start and record.date_end and record.target_amount:
                total_days = (record.date_end - record.date_start).days + 1
                if today < record.date_start:
                    elapsed_days = 0
                elif today > record.date_end:
                    elapsed_days = total_days
                else:
                    elapsed_days = (today - record.date_start).days + 1
                if total_days > 0:
                    time_ratio = elapsed_days / total_days
                    record.theoretical_amount = record.target_amount * time_ratio
                    record.theoretical_percent = time_ratio
                    if record.achieved_amount >= record.target_amount:
                        record.theoretical_status = 'completed'
                    elif record.achieved_amount >= record.theoretical_amount:
                        record.theoretical_status = 'on_track'
                    else:
                        record.theoretical_status = 'below'
                else:
                    record.theoretical_amount = 0.0
                    record.theoretical_percent = 0.0
                    record.theoretical_status = 'below'
            else:
                record.theoretical_amount = 0.0
                record.theoretical_percent = 0.0
                record.theoretical_status = 'below'

    @api.depends('target_point', 'date_start', 'date_end', 'team_ids', 'currency_id')
    def _compute_invoice_amounts(self):
        for record in self:
            invoiced = 0.0
            if record.target_point in ('invoice_validate', 'invoice_paid'):
                domain = record._get_invoice_domain()
                invoices = record.env['account.move'].search(domain)
                invoiced = sum(invoices.mapped('amount_total'))
            record.invoiced_amount = invoiced
            record.invoice_percent = invoiced / record.target_amount if record.target_amount else 0.0

    @api.depends('target_point', 'date_start', 'date_end', 'team_ids')
    def _compute_related_lines(self):
        for record in self:
            if record.target_point == 'sale_order':
                domain = record._get_sale_order_domain()
                orders = record.env['sale.order'].search(domain)
                record.sale_order_line_ids = orders.mapped('order_line').ids
                record.invoice_line_ids = []
            elif record.target_point in ('invoice_validate', 'invoice_paid'):
                domain = record._get_invoice_domain()
                invoices = record.env['account.move'].search(domain)
                record.invoice_line_ids = invoices.mapped('invoice_line_ids').ids
                record.sale_order_line_ids = []
            else:
                record.sale_order_line_ids = []
                record.invoice_line_ids = []

    @api.depends('target_point', 'date_start', 'date_end', 'team_ids')
    def _compute_counters(self):
        for record in self:
            if not record.date_start or not record.date_end:
                record.sale_order_count = 0
                record.sale_order_line_count = 0
                record.invoice_count = 0
                record.invoice_line_count = 0
                continue
            if record.target_point == 'sale_order':
                sale_domain = record._get_sale_order_domain()
                sale_orders = record.env['sale.order'].search(sale_domain)
                record.sale_order_count = len(sale_orders)
                record.sale_order_line_count = len(sale_orders.mapped('order_line'))
                record.invoice_count = 0
                record.invoice_line_count = 0
            elif record.target_point in ('invoice_validate', 'invoice_paid'):
                invoice_domain = record._get_invoice_domain()
                invoices = record.env['account.move'].search(invoice_domain)
                record.invoice_count = len(invoices)
                record.invoice_line_count = len(invoices.mapped('invoice_line_ids'))
                record.sale_order_count = 0
                record.sale_order_line_count = 0
            else:
                record.sale_order_count = 0
                record.sale_order_line_count = 0
                record.invoice_count = 0
                record.invoice_line_count = 0

    def _get_sale_order_domain(self):
        domain = [
            ('date_order', '>=', self.date_start),
            ('date_order', '<=', self.date_end),
            ('state', 'in', ['sale', 'done']),
        ]
        if self.team_ids:
            domain.append(('team_id', 'in', self.team_ids.ids))
        if self.currency_id:
            domain.append(('currency_id', '=', self.currency_id.id))
        return domain

    def _get_invoice_domain(self):
        domain = [
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', 'not in', ['draft', 'cancel']),
        ]
        if self.target_point == 'invoice_validate':
            domain.extend([
                ('invoice_date', '>=', self.date_start),
                ('invoice_date', '<=', self.date_end),
            ])
        elif self.target_point == 'invoice_paid':
            domain.extend([
                ('invoice_date', '>=', self.date_start),
                ('invoice_date', '<=', self.date_end),
                ('payment_state', 'in', ['paid', 'in_payment']),
            ])
        if self.team_ids:
            domain.append(('team_id', 'in', self.team_ids.ids))
        if self.currency_id:
            domain.append(('currency_id', '=', self.currency_id.id))
        return domain

    def action_view_sale_orders(self):
        domain = self._get_sale_order_domain()
        return {
            'name': _('Sale Orders - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'default_team_id': self.team_ids[:1].id if self.team_ids else False,
            },
        }

    def action_view_sale_order_lines(self):
        domain = self._get_sale_order_domain()
        orders = self.env['sale.order'].search(domain)
        return {
            'name': _('Sale Order Lines - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.line',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', orders.mapped('order_line').ids)],
        }

    def action_view_invoices(self):
        domain = self._get_invoice_domain()
        return {
            'name': _('Invoices - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': domain,
        }

    def action_view_invoice_lines(self):
        domain = self._get_invoice_domain()
        invoices = self.env['account.move'].search(domain)
        return {
            'name': _('Invoice Lines - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', invoices.mapped('invoice_line_ids').ids)],
            'context': {'group_by': 'move_id'},
        }

    def action_confirm(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft targets can be confirmed.'))
            record.state = 'confirmed'
            record.message_post(body=_('Team target confirmed.'))
        self._send_notification_email('confirm')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Target has been confirmed successfully.'),
                'type': 'success',
            },
        }

    def action_close(self):
        for record in self:
            if record.state not in ('draft', 'confirmed'):
                raise UserError(_('Only draft or confirmed targets can be closed.'))
            record.state = 'closed'
            record.message_post(body=_('Team target closed.'))
        self._send_notification_email('close')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Target has been closed successfully.'),
                'type': 'success',
            },
        }

    def action_reset_to_draft(self):
        for record in self:
            record.state = 'draft'
            record.message_post(body=_('Team target reset to draft.'))

    def action_send_mail(self):
        self._send_notification_email('manual')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Achievement notification email has been sent.'),
            },
        }

    def _send_notification_email(self, action_type):
        if not self:
            return
        template_mapping = {
            'confirm': 'sale_target.email_template_team_target_confirmed',
            'close': 'sale_target.email_template_team_target_closed',
            'manual': 'sale_target.email_template_team_target_manual',
        }
        xml_id = template_mapping.get(action_type)
        if not xml_id:
            return
        try:
            template = self.env.ref(xml_id)
            if template:
                for record in self:
                    if record.responsible_id and record.responsible_id.email:
                        template.send_mail(record.id, force_send=True)
        except Exception as e:
            _logger.warning("Failed to send email notification: %s", str(e))

    def action_recompute_achievement(self):
        for record in self:
            record._compute_achieved_amount()
            record._compute_percent_achieved()
            record._compute_theoretical_achievement()
            record._compute_invoice_amounts()
            record._compute_counters()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Achievement calculations have been recomputed successfully.'),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_end and record.date_start > record.date_end:
                raise ValidationError(_('Start date must be before end date.'))

    @api.constrains('target_amount')
    def _check_target_amount(self):
        for record in self:
            if record.target_amount <= 0:
                raise ValidationError(_('Target amount must be greater than zero.'))

    @api.constrains('team_ids', 'date_start', 'date_end', 'target_point')
    def _check_duplicate_targets(self):
        for record in self:
            if not record.team_ids:
                continue
            overlapping = self.search([
                ('id', '!=', record.id),
                ('date_start', '<=', record.date_end),
                ('date_end', '>=', record.date_start),
                ('target_point', '=', record.target_point),
                ('state', '!=', 'closed'),
            ])
            for other in overlapping:
                if other.team_ids & record.team_ids:
                    raise ValidationError(_(
                        'A team target with overlapping dates already exists for one or more of the selected teams and target point.'
                    ))
