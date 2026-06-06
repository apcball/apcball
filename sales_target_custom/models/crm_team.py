from odoo import models, fields, api
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    target_amount_total = fields.Monetary(
        string='Team Target',
        compute='_compute_team_target',
        currency_field='currency_id',
    )
    achieved_amount_total = fields.Monetary(
        string='Team Achieved',
        compute='_compute_team_target',
        currency_field='currency_id',
    )
    remaining_amount = fields.Monetary(
        string='Remaining',
        compute='_compute_team_target',
        currency_field='currency_id',
    )
    target_percent = fields.Float(
        string='Achievement %',
        compute='_compute_team_target',
    )
    target_status = fields.Selection([
        ('achieved', 'Achieved'),
        ('on_track', 'On Track'),
        ('at_risk', 'At Risk'),
        ('behind', 'Behind Target'),
        ('no_target', 'No Target'),
    ], string='Status', compute='_compute_team_target')
    active_target_count = fields.Integer(
        string='Active Targets',
        compute='_compute_team_target',
    )

    @api.depends()
    def _compute_team_target(self):
        SalesTarget = self.env['sales.target'].sudo()
        today = date.today()
        for team in self:
            member_ids = team.member_ids.ids
            if team.user_id:
                member_ids.append(team.user_id.id)
            member_ids = list(set(member_ids))

            domain = [
                ('state', '=', 'confirmed'),
                ('date_start', '<=', today),
                ('date_end', '>=', today),
                '|',
                ('team_ids', 'in', team.id),
                ('user_id', 'in', member_ids),
            ]
            targets = SalesTarget.search(domain)
            if not targets:
                team.update({
                    'target_amount_total': 0.0,
                    'achieved_amount_total': 0.0,
                    'remaining_amount': 0.0,
                    'target_percent': 0.0,
                    'target_status': 'no_target',
                    'active_target_count': 0,
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

            team.update({
                'target_amount_total': total_target,
                'achieved_amount_total': total_achieved,
                'remaining_amount': max(total_target - total_achieved, 0.0),
                'target_percent': percent,
                'target_status': status,
                'active_target_count': len(targets),
            })
