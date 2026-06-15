from odoo import models, fields, api
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    target_amount_total = fields.Monetary(
        string='My Target',
        compute='_compute_my_target',
        currency_field='currency_id',
    )
    achieved_amount_total = fields.Monetary(
        string='My Achieved',
        compute='_compute_my_target',
        currency_field='currency_id',
    )
    remaining_amount = fields.Monetary(
        string='Remaining',
        compute='_compute_my_target',
        currency_field='currency_id',
    )
    target_percent = fields.Float(
        string='Achievement %',
        compute='_compute_my_target',
    )
    target_status = fields.Selection([
        ('achieved', 'Achieved'),
        ('on_track', 'On Track'),
        ('at_risk', 'At Risk'),
        ('behind', 'Behind Target'),
        ('no_target', 'No Target'),
    ], string='Target Status', compute='_compute_my_target', store=False, default='no_target')
    active_target_count = fields.Integer(
        string='Active Targets',
        compute='_compute_my_target',
    )
    my_sale_order_count = fields.Integer(
        string='Sale Orders',
        compute='_compute_my_target',
    )
    my_invoice_count = fields.Integer(
        string='My Invoices',
        compute='_compute_my_target',
    )
    my_delivery_order_count = fields.Integer(
        string='Delivery Orders',
        compute='_compute_my_target',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )

    @api.depends()
    def _compute_my_target(self):
        SalesTarget = self.env['sales.target'].sudo()
        today = date.today()
        for user in self:
            targets = SalesTarget.search([
                ('user_id', '=', user.id),
                ('state', '=', 'confirmed'),
                ('date_start', '<=', today),
                ('date_end', '>=', today),
                ('team_ids', '=', False),
            ])
            if not targets:
                user.update({
                    'target_amount_total': 0.0,
                    'achieved_amount_total': 0.0,
                    'remaining_amount': 0.0,
                    'target_percent': 0.0,
                    'target_status': 'no_target',
                    'active_target_count': 0,
                    'my_sale_order_count': 0,
                    'my_invoice_count': 0,
                    'my_delivery_order_count': 0,
                })
                continue

            total_target = sum(targets.mapped('target_amount'))
            total_achieved = sum(targets.mapped('achieved_amount'))
            percent = (total_achieved / total_target * 100) if total_target else 0.0

            if percent >= 100:
                status = 'achieved'
            elif percent >= 75:
                status = 'on_track'
            elif percent >= 50:
                status = 'at_risk'
            else:
                status = 'behind'

            user.update({
                'target_amount_total': total_target,
                'achieved_amount_total': total_achieved,
                'remaining_amount': max(total_target - total_achieved, 0.0),
                'target_percent': percent,
                'target_status': status,
                'active_target_count': len(targets),
                'my_sale_order_count': sum(targets.mapped('sale_order_count')),
                'my_invoice_count': sum(targets.mapped('invoice_count')),
                'my_delivery_order_count': sum(targets.mapped('delivery_order_count')),
            })
