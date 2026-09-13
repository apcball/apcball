from collections import Counter
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class ITManagementDashboard(models.AbstractModel):
    _name = 'buz.it.management.dashboard'
    _description = 'IT Management Dashboard'

    _TARGETS = {
        'open_tickets', 'urgent_tickets', 'ticket_status',
        'ticket_trend_opened', 'ticket_trend_closed', 'recent_tickets',
        'unassigned_tickets', 'overdue_sla', 'needs_attention',
        'assets_assigned', 'assets_available', 'assets_repair',
        'asset_status', 'asset_category', 'repair_backlog',
        'licenses_expiring', 'licenses_expired', 'license_seats',
    }

    @api.model
    def _ensure_dashboard_access(self):
        if not self.env.user.has_group(
            'buz_it_helpdesk.group_it_support_agent'
        ):
            raise AccessError('Only IT Support Agents can access this dashboard.')

    @api.model
    def _normalize_filters(self, filters=None):
        filters = filters or {}
        allowed_ids = set(self.env.companies.ids)
        requested_ids = {
            int(company_id)
            for company_id in (filters.get('company_ids') or self.env.companies.ids)
        }
        if not requested_ids or not requested_ids.issubset(allowed_ids):
            raise UserError('One or more selected companies are not allowed.')

        today = fields.Date.context_today(self)
        period = filters.get('period') or 'this_month'
        if period == 'last_30_days':
            date_from = today - timedelta(days=29)
        elif period == 'last_90_days':
            date_from = today - timedelta(days=89)
        elif period == 'this_year':
            date_from = today.replace(month=1, day=1)
        else:
            period = 'this_month'
            date_from = today.replace(day=1)

        return {
            'period': period,
            'date_from': date_from,
            'date_to': today,
            'company_ids': sorted(requested_ids),
        }

    @api.model
    def _ticket_base_domain(self, normalized):
        draft = self.env.ref('buz_it_helpdesk.stage_draft')
        return [
            ('active', '=', True),
            ('company_id', 'in', normalized['company_ids']),
            ('stage_id', '!=', draft.id),
        ]

    @api.model
    def _date_rows(self, date_from, date_to, opened, closed):
        rows = []
        cursor = date_from
        while cursor <= date_to:
            rows.append({
                'date': cursor.isoformat(),
                'label': cursor.strftime('%d %b'),
                'opened': opened.get(cursor, 0),
                'closed': closed.get(cursor, 0),
            })
            cursor += timedelta(days=1)
        return rows

    @api.model
    def _ticket_trend(self, normalized):
        model = self.env['buz.helpdesk.ticket']
        domain = self._ticket_base_domain(normalized)
        opened = Counter()
        closed = Counter()
        for row in model.search_read(
            domain + [
                ('create_ticket_date', '>=', normalized['date_from']),
                ('create_ticket_date', '<=', normalized['date_to']),
            ],
            ['create_ticket_date'],
        ):
            if row['create_ticket_date']:
                opened[fields.Date.to_date(row['create_ticket_date'])] += 1
        for row in model.search_read(
            domain + [
                ('closed_ticket_date', '>=', normalized['date_from']),
                ('closed_ticket_date', '<=', normalized['date_to']),
            ],
            ['closed_ticket_date'],
        ):
            if row['closed_ticket_date']:
                closed[fields.Date.to_date(row['closed_ticket_date'])] += 1
        return self._date_rows(
            normalized['date_from'], normalized['date_to'], opened, closed
        )

    @api.model
    def _ticket_status(self, normalized):
        model = self.env['buz.helpdesk.ticket']
        stages = [
            ('New', 'buz_it_helpdesk.stage_new'),
            ('In Progress', 'buz_it_helpdesk.stage_in_progress'),
            ('Pending User', 'buz_it_helpdesk.stage_pending_user'),
            ('Resolved', 'buz_it_helpdesk.stage_resolved'),
            ('Closed', 'buz_it_helpdesk.stage_closed'),
        ]
        base = self._ticket_base_domain(normalized)
        return [
            {
                'label': label,
                'stage_id': self.env.ref(xmlid).id,
                'value': model.search_count(
                    base + [('stage_id', '=', self.env.ref(xmlid).id)]
                ),
            }
            for label, xmlid in stages
        ]

    @api.model
    def _asset_status(self, normalized):
        model = self.env['buz.it.asset']
        base = [('active', '=', True), ('company_id', 'in', normalized['company_ids'])]
        states = [
            ('Available', 'available'), ('Assigned', 'assigned'),
            ('Repair', 'repair'), ('Retired', 'retired'), ('Lost', 'lost'),
        ]
        return [
            {
                'label': label, 'state': state,
                'value': model.search_count(base + [('state', '=', state)]),
            }
            for label, state in states
        ]

    @api.model
    def _asset_categories(self, normalized):
        model = self.env['buz.it.asset']
        rows = model.search_read(
            [('active', '=', True), ('company_id', 'in', normalized['company_ids'])],
            ['category_id']
        )
        counts = Counter()
        names = {}
        uncategorized = 0
        for row in rows:
            category = row['category_id']
            if category:
                category_id, category_name = category
                counts[category_id] += 1
                names[category_id] = category_name
            else:
                uncategorized += 1
        result = [
            {
                'category_id': category_id,
                'label': names[category_id],
                'value': counts[category_id],
            }
            for category_id in counts
        ]
        if uncategorized:
            result.append({
                'category_id': False,
                'label': 'Uncategorized',
                'value': uncategorized,
            })
        return result

    @api.model
    def _license_seats(self, normalized):
        licenses = self.env['buz.it.software.license'].search([
            ('company_id', 'in', normalized['company_ids']),
            ('active', '=', True),
        ])
        total = sum(record.seat_count for record in licenses)
        used = sum(record.active_installation_count for record in licenses)
        unlimited = sum(1 for record in licenses if not record.seat_count)
        overallocated = sum(
            max(record.active_installation_count - record.seat_count, 0)
            for record in licenses if record.seat_count
        )
        return {
            'used': used,
            'available': max(total - used, 0),
            'total': total,
            'unlimited_licenses': unlimited,
            'overallocated': overallocated,
        }

    @api.model
    def _human_duration(self, seconds):
        minutes = max(int(seconds // 60), 1)
        days, minutes = divmod(minutes, 24 * 60)
        hours, minutes = divmod(minutes, 60)
        parts = []
        if days:
            parts.append(f'{days} วัน')
        if hours:
            parts.append(f'{hours} ชั่วโมง')
        if minutes and len(parts) < 2:
            parts.append(f'{minutes} นาที')
        return 'เกิน ' + ' '.join(parts)

    @api.model
    def _format_user_datetime(self, value):
        if not value:
            return ''
        local_value = fields.Datetime.context_timestamp(self, value)
        return local_value.strftime('%Y-%m-%d %H:%M')

    @api.model
    def _overdue_sla(self, normalized):
        ticket_model = self.env['buz.helpdesk.ticket']
        terminal_stages = [
            self.env.ref('buz_it_helpdesk.stage_draft').id,
            self.env.ref('buz_it_helpdesk.stage_resolved').id,
            self.env.ref('buz_it_helpdesk.stage_closed').id,
        ]
        tickets = ticket_model.search([
            ('active', '=', True),
            ('company_id', 'in', normalized['company_ids']),
            ('stage_id', 'not in', terminal_stages),
        ])
        now = fields.Datetime.now()
        rows = []
        for ticket in tickets:
            if ticket.sla_status in ('no_sla', 'paused', 'resolved'):
                continue
            deadlines = []
            for label, deadline, completed in (
                ('Response', ticket.sla_response_deadline, ticket.sla_response_at),
                ('Resolution', ticket.sla_resolution_deadline, ticket.sla_resolution_at),
            ):
                if deadline and not completed and deadline < now:
                    deadlines.append((label, deadline))
            if not deadlines:
                continue
            overdue_seconds = max((now - deadline).total_seconds() for _, deadline in deadlines)
            rows.append({
                'id': ticket.id,
                'target': 'overdue_sla',
                'bucket': {'record_id': ticket.id},
                'title': ticket.display_name,
                'detail': ticket.subject,
                'sla_details': [
                    {
                        'type': label,
                        'deadline': self._format_user_datetime(deadline),
                        'duration': self._human_duration(
                            (now - deadline).total_seconds()
                        ),
                    }
                    for label, deadline in deadlines
                ],
                'assignee': ticket.assigned_user_id.name or 'Unassigned',
                'overdue_seconds': overdue_seconds,
                'status': ticket.stage_id.name,
                'priority': ticket.priority,
            })
        rows.sort(key=lambda row: (-row['overdue_seconds'], row['id']))
        return rows

    @api.model
    def _needs_attention(self, normalized):
        ticket_model = self.env['buz.helpdesk.ticket']
        repair_model = self.env['buz.it.asset.maintenance']
        license_model = self.env['buz.it.software.license']
        ticket_base = self._ticket_base_domain(normalized)
        closed = self.env.ref('buz_it_helpdesk.stage_closed')
        resolved = self.env.ref('buz_it_helpdesk.stage_resolved')
        urgent = ticket_model.search(
            ticket_base + [
                ('stage_id', 'not in', [closed.id, resolved.id]),
                ('priority', '=', '3'),
            ],
            order='create_ticket_date asc, id asc', limit=5,
        )
        unassigned = ticket_model.search(
            ticket_base + [('assigned_user_id', '=', False)],
            order='create_ticket_date asc, id asc', limit=5,
        )
        repairs = repair_model.search([
            ('active', '=', True),
            ('company_id', 'in', normalized['company_ids']),
            ('state', 'in', ['sent', 'in_progress']),
        ], order='sent_date asc, id asc', limit=5)
        today = normalized['date_to']
        expiring = license_model.search([
            ('company_id', 'in', normalized['company_ids']),
            ('active', '=', True),
            ('expiration_date', '>=', today),
            ('expiration_date', '<=', today + timedelta(days=30)),
        ], order='expiration_date asc, id asc', limit=5)
        return {
            'urgent_tickets': [
                {
                    'id': ticket.id, 'target': 'urgent_tickets',
                    'bucket': {'record_id': ticket.id},
                    'title': ticket.display_name, 'detail': ticket.subject,
                    'status': ticket.stage_id.name, 'priority': ticket.priority,
                } for ticket in urgent[:2]
            ],
            'repairs': [
                {
                    'id': repair.id, 'target': 'repair_backlog',
                    'bucket': {'record_id': repair.id},
                    'title': repair.asset_id.display_name, 'detail': repair.symptom,
                    'status': repair.state, 'priority': None,
                } for repair in repairs
            ],
            'licenses': [
                {
                    'id': record.id, 'target': 'licenses_expiring',
                    'bucket': {'record_id': record.id},
                    'title': record.display_name,
                    'detail': record.expiration_date.isoformat(),
                    'status': 'Expiring', 'priority': None,
                } for record in expiring
            ],
            'unassigned_tickets': [
                {
                    'id': ticket.id, 'target': 'unassigned_tickets',
                    'bucket': {'record_id': ticket.id},
                    'title': ticket.display_name, 'detail': ticket.subject,
                    'status': ticket.stage_id.name, 'priority': ticket.priority,
                } for ticket in unassigned
            ],
            'sla': self._overdue_sla(normalized)[:2],
        }

    @api.model
    def _recent_tickets(self, normalized):
        model = self.env['buz.helpdesk.ticket']
        rows = model.search_read(
            self._ticket_base_domain(normalized),
            [
                'name', 'subject', 'priority', 'assigned_user_id',
                'stage_id', 'create_ticket_date',
            ],
            order='create_date desc, id desc', limit=8,
        )
        priorities = {'0': 'Low', '1': 'Normal', '2': 'High', '3': 'Urgent'}
        return [
            {
                'id': row['id'], 'name': row['name'], 'subject': row['subject'],
                'priority': priorities.get(row['priority'], row['priority']),
                'assigned_to': (
                    row['assigned_user_id'][1]
                    if row['assigned_user_id'] else 'Unassigned'
                ),
                'stage': row['stage_id'][1] if row['stage_id'] else '',
                'stage_id': row['stage_id'][0] if row['stage_id'] else False,
                'create_ticket_date': row['create_ticket_date'],
                'target': 'recent_tickets',
                'bucket': {'record_id': row['id']},
            }
            for row in rows
        ]

    @api.model
    def get_dashboard_data(self, filters=None):
        self._ensure_dashboard_access()
        normalized = self._normalize_filters(filters)
        ticket_model = self.env['buz.helpdesk.ticket']
        base = self._ticket_base_domain(normalized)
        closed = self.env.ref('buz_it_helpdesk.stage_closed')
        resolved = self.env.ref('buz_it_helpdesk.stage_resolved')
        open_domain = base + [('stage_id', 'not in', [closed.id, resolved.id])]
        new_ticket_domain = base + [
            ('stage_id', '=', self.env.ref('buz_it_helpdesk.stage_new').id),
        ]
        asset_model = self.env['buz.it.asset']
        asset_base = [('active', '=', True), ('company_id', 'in', normalized['company_ids'])]
        today = normalized['date_to']
        expiring_domain = [
            ('company_id', 'in', normalized['company_ids']),
            ('active', '=', True),
            ('expiration_date', '>=', today),
            ('expiration_date', '<=', today + timedelta(days=30)),
        ]
        expired_domain = [
            ('company_id', 'in', normalized['company_ids']),
            ('active', '=', True),
            ('expiration_date', '<', today),
        ]
        overdue_sla = self._overdue_sla(normalized)
        return {
            'meta': {
                'period': normalized['period'],
                'date_from': normalized['date_from'].isoformat(),
                'date_to': normalized['date_to'].isoformat(),
                'company_ids': normalized['company_ids'],
                'license_expiry_days': 30,
            },
            'companies': [
                {'id': company.id, 'name': company.name}
                for company in self.env.companies
            ],
            'kpis': {
                'open_tickets': ticket_model.search_count(new_ticket_domain),
                'urgent_tickets': ticket_model.search_count(
                    open_domain + [('priority', '=', '3')]
                ),
                'unassigned_tickets': ticket_model.search_count(
                    base + [('assigned_user_id', '=', False)]
                ),
                'overdue_sla': len(overdue_sla),
                'assets_assigned': asset_model.search_count(
                    asset_base + [('state', '=', 'assigned')]
                ),
                'assets_available': asset_model.search_count(
                    asset_base + [('state', '=', 'available')]
                ),
                'assets_repair': asset_model.search_count(
                    asset_base + [('state', '=', 'repair')]
                ),
                'licenses_expiring': self.env[
                    'buz.it.software.license'
                ].search_count(expiring_domain),
                'licenses_expired': self.env[
                    'buz.it.software.license'
                ].search_count(expired_domain),
            },
            'ticket_trend': self._ticket_trend(normalized),
            'ticket_status': self._ticket_status(normalized),
            'asset_status': self._asset_status(normalized),
            'assets_by_category': self._asset_categories(normalized),
            'license_seats': self._license_seats(normalized),
            'needs_attention': self._needs_attention(normalized),
            'recent_tickets': self._recent_tickets(normalized),
        }

    @api.model
    def get_drilldown_action(self, target, filters=None, bucket=None):
        self._ensure_dashboard_access()
        normalized = self._normalize_filters(filters)
        if target not in self._TARGETS:
            raise UserError('Unsupported dashboard drill-down target.')

        if isinstance(bucket, dict) and bucket.get('record_id'):
            record_models = {
                'recent_tickets': 'buz.helpdesk.ticket',
                'urgent_tickets': 'buz.helpdesk.ticket',
                'unassigned_tickets': 'buz.helpdesk.ticket',
                'overdue_sla': 'buz.helpdesk.ticket',
                'repair_backlog': 'buz.it.asset.maintenance',
                'licenses_expiring': 'buz.it.software.license',
            }
            model = record_models.get(target)
            if model:
                record_domain = [('id', '=', int(bucket['record_id']))]
                if model == 'buz.helpdesk.ticket':
                    record_domain += self._ticket_base_domain(normalized)
                else:
                    record_domain += [
                        ('active', '=', True),
                        ('company_id', 'in', normalized['company_ids']),
                    ]
                record = self.env[model].search(record_domain, limit=1)
                if not record:
                    raise AccessError('The selected dashboard record is not allowed.')
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Dashboard Details',
                    'res_model': model,
                    'res_id': record.id,
                    'view_mode': 'form',
                    'views': [[False, 'form']],
                    'context': {'active_test': True},
                }

        ticket_model = 'buz.helpdesk.ticket'
        asset_model = 'buz.it.asset'
        model = ticket_model
        name = 'Dashboard Details'
        context = {'active_test': True}
        ticket_base = self._ticket_base_domain(normalized)
        closed = self.env.ref('buz_it_helpdesk.stage_closed')
        if target == 'open_tickets':
            name, domain = 'Open Tickets', ticket_base + [
                ('stage_id', '=', self.env.ref('buz_it_helpdesk.stage_new').id),
            ]
        elif target == 'urgent_tickets':
            name, domain = 'Urgent Tickets', ticket_base + [
                ('stage_id', 'not in', [closed.id, self.env.ref(
                    'buz_it_helpdesk.stage_resolved'
                ).id]), ('priority', '=', '3'),
            ]
        elif target == 'unassigned_tickets':
            name, domain = 'Unassigned Tickets', ticket_base + [
                ('assigned_user_id', '=', False),
            ]
        elif target == 'overdue_sla':
            overdue_ids = [
                row['id'] for row in self._overdue_sla(normalized)
            ]
            name, domain = 'Overdue SLA', [('id', 'in', overdue_ids)]
        elif target == 'needs_attention':
            overdue_ids = [
                row['id'] for row in self._overdue_sla(normalized)
            ]
            resolved = self.env.ref('buz_it_helpdesk.stage_resolved')
            name, domain = 'Needs Attention', ticket_base + [
                '|', '&',
                ('stage_id', 'not in', [closed.id, resolved.id]),
                ('priority', '=', '3'),
                ('id', 'in', overdue_ids),
            ]
        elif target in (
            'ticket_status', 'ticket_trend_opened',
            'ticket_trend_closed', 'recent_tickets',
        ):
            name, domain = 'Ticket Details', ticket_base
            if target == 'ticket_status' and bucket:
                domain.append(('stage_id', '=', int(bucket)))
            elif target.startswith('ticket_trend_') and bucket:
                field_name = (
                    'create_ticket_date'
                    if target.endswith('opened') else 'closed_ticket_date'
                )
                domain.append((field_name, '=', bucket))
            elif target == 'recent_tickets':
                domain.append(('create_ticket_date', '>=', normalized['date_from']))
        elif target in ('assets_assigned', 'assets_available', 'assets_repair'):
            states = {
                'assets_assigned': ('assigned', 'Assigned Assets'),
                'assets_available': ('available', 'Available Assets'),
                'assets_repair': ('repair', 'Assets Under Repair'),
            }
            state, name = states[target]
            model, domain = asset_model, [
                ('active', '=', True),
                ('company_id', 'in', normalized['company_ids']),
                ('state', '=', state),
            ]
        elif target == 'asset_status':
            name, domain = 'Asset Status', [
                ('active', '=', True),
                ('company_id', 'in', normalized['company_ids']),
            ]
            model = asset_model
            if bucket:
                domain.append(('state', '=', bucket))
        elif target == 'asset_category':
            name, domain = 'Assets by Category', [
                ('active', '=', True),
                ('company_id', 'in', normalized['company_ids']),
            ]
            model = asset_model
            category_id = bucket.get('category_id') if isinstance(bucket, dict) else bucket
            domain.append(
                ('category_id', '=', int(category_id)) if category_id
                else ('category_id', '=', False)
            )
        elif target == 'repair_backlog':
            name, model, domain = 'Repair Backlog', 'buz.it.asset.maintenance', [
                ('active', '=', True),
                ('company_id', 'in', normalized['company_ids']),
                ('state', 'in', ['sent', 'in_progress']),
            ]
        elif target == 'licenses_expiring':
            name, model, domain = 'Expiring Licenses', 'buz.it.software.license', [
                ('company_id', 'in', normalized['company_ids']),
                ('active', '=', True),
                ('expiration_date', '>=', normalized['date_to']),
                ('expiration_date', '<=', normalized['date_to'] + timedelta(days=30)),
            ]
        elif target == 'licenses_expired':
            name, model, domain = 'Expired Licenses', 'buz.it.software.license', [
                ('company_id', 'in', normalized['company_ids']),
                ('active', '=', True),
                ('expiration_date', '<', normalized['date_to']),
            ]
        elif target == 'license_seats':
            name, model, domain = 'Software Licenses', 'buz.it.software.license', [
                ('company_id', 'in', normalized['company_ids']),
                ('active', '=', True),
            ]

        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': domain,
            'context': context,
        }
