from datetime import datetime, time, timedelta
import math

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


SLA_GROUPS = 'buz_it_helpdesk.group_it_support_agent'


class HelpdeskSlaConfig(models.Model):
    _name = 'buz.helpdesk.sla.config'
    _description = 'Helpdesk SLA Settings'
    _order = 'company_id, id'

    name = fields.Char(required=True, default='SLA Settings')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        index=True,
    )
    timezone = fields.Char(required=True, default='Asia/Bangkok')
    work_start = fields.Float(string='Work Start', required=True, default=8.0)
    work_end = fields.Float(string='Work End', required=True, default=17.0)
    lunch_start = fields.Float(string='Lunch Start', required=True, default=12.0)
    lunch_end = fields.Float(string='Lunch End', required=True, default=13.0)
    holiday_ids = fields.One2many(
        'buz.helpdesk.sla.holiday', 'config_id', string='Company Holidays',
    )
    rule_ids = fields.One2many(
        'buz.helpdesk.sla.rule', 'config_id', string='SLA Rules',
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('company_unique', 'unique(company_id)',
         'Only one SLA Settings record is allowed per company.'),
    ]

    @api.constrains(
        'timezone', 'work_start', 'work_end', 'lunch_start', 'lunch_end',
    )
    def _check_working_hours(self):
        for config in self:
            config._validate_timezone()
            work_start = config._hours_to_minutes(
                config.work_start, 'Work Start', allow_24=False,
            )
            work_end = config._hours_to_minutes(
                config.work_end, 'Work End', allow_24=True,
            )
            lunch_start = config._hours_to_minutes(
                config.lunch_start, 'Lunch Start', allow_24=False,
            )
            lunch_end = config._hours_to_minutes(
                config.lunch_end, 'Lunch End', allow_24=False,
            )
            if not work_start < work_end:
                raise ValidationError(_(
                    'Work Start must be earlier than Work End.'
                ))
            if not work_start <= lunch_start < lunch_end <= work_end:
                raise ValidationError(_(
                    'Lunch Start and Lunch End must be inside working hours.'
                ))

    def _validate_timezone(self):
        self.ensure_one()
        if not self.timezone or self.timezone not in pytz.all_timezones:
            raise ValidationError(_(
                'Timezone "%(timezone)s" is not supported. Select a timezone '
                'from the supported timezone list.',
                timezone=self.timezone or _('empty'),
            ))

    def _is_valid_for_calculation(self):
        """Return False for incomplete legacy data instead of making a deadline."""
        self.ensure_one()
        try:
            self._validate_timezone()
            work_start = self._hours_to_minutes(
                self.work_start, 'Work Start', allow_24=False,
            )
            work_end = self._hours_to_minutes(
                self.work_end, 'Work End', allow_24=True,
            )
            lunch_start = self._hours_to_minutes(
                self.lunch_start, 'Lunch Start', allow_24=False,
            )
            lunch_end = self._hours_to_minutes(
                self.lunch_end, 'Lunch End', allow_24=False,
            )
        except ValidationError:
            return False
        return (
            work_start < work_end
            and work_start <= lunch_start < lunch_end <= work_end
        )

    def _hours_to_minutes(self, value, label, allow_24=False):
        """แปลงชั่วโมงแบบ Float เป็นนาที และตรวจรูปแบบก่อนคำนวณเวลา."""
        self.ensure_one()
        if value is None or not math.isfinite(value):
            raise ValidationError(_('%(label)s must be a valid time.', label=label))
        maximum = 24 * 60 if allow_24 else (24 * 60) - 1
        total_minutes = value * 60
        rounded_minutes = round(total_minutes)
        if (
            value < 0
            or value > 24
            or abs(total_minutes - rounded_minutes) > 1e-6
            or rounded_minutes > maximum
        ):
            raise ValidationError(_(
                '%(label)s must be a valid time in HH:MM format.', label=label,
            ))
        return rounded_minutes

    def _local_datetime(self, local_date, value, label, allow_24=False):
        total_minutes = self._hours_to_minutes(value, label, allow_24=allow_24)
        if total_minutes == 24 * 60:
            return datetime.combine(local_date + timedelta(days=1), time.min)
        hours, minutes = divmod(total_minutes, 60)
        return datetime.combine(local_date, time(hours, minutes))

    def _localize(self, value, tz):
        return tz.localize(value, is_dst=None)

    def _is_workday(self, local_date):
        self.ensure_one()
        return (
            local_date.weekday() < 5
            and not self.env['buz.helpdesk.sla.holiday'].search_count([
                ('config_id', '=', self.id), ('date', '=', local_date),
            ])
        )

    def _work_intervals(self, local_date, tz):
        if not self._is_workday(local_date):
            return []
        return [
            (self._localize(self._local_datetime(
                local_date, self.work_start, 'Work Start', allow_24=False,
            ), tz), self._localize(self._local_datetime(
                local_date, self.lunch_start, 'Lunch Start', allow_24=False,
            ), tz)),
            (self._localize(self._local_datetime(
                local_date, self.lunch_end, 'Lunch End', allow_24=False,
            ), tz), self._localize(self._local_datetime(
                local_date, self.work_end, 'Work End', allow_24=True,
            ), tz)),
        ]

    def business_minutes_between(self, start, end):
        """Return working minutes between naive UTC datetimes."""
        self.ensure_one()
        if not start or not end or end <= start:
            return 0.0
        self._validate_timezone()
        tz = pytz.timezone(self.timezone)
        utc = pytz.UTC
        start_local = utc.localize(start).astimezone(tz)
        end_local = utc.localize(end).astimezone(tz)
        total = 0.0
        current = start_local.date()
        while current <= end_local.date():
            for interval_start, interval_end in self._work_intervals(current, tz):
                left = max(start_local, interval_start)
                right = min(end_local, interval_end)
                if right > left:
                    total += (right - left).total_seconds() / 60
            current += timedelta(days=1)
        return total

    def add_business_minutes(self, start, minutes):
        """Add working minutes and return a naive UTC datetime."""
        self.ensure_one()
        if not start or minutes <= 0:
            return start
        self._validate_timezone()
        tz = pytz.timezone(self.timezone)
        utc = pytz.UTC
        current = utc.localize(start).astimezone(tz)
        remaining = float(minutes)
        while remaining > 0:
            intervals = self._work_intervals(current.date(), tz)
            for interval_start, interval_end in intervals:
                cursor = max(current, interval_start)
                if cursor >= interval_end:
                    continue
                available = (interval_end - cursor).total_seconds() / 60
                if remaining <= available:
                    result = cursor + timedelta(minutes=remaining)
                    return result.astimezone(utc).replace(tzinfo=None)
                remaining -= available
            current = tz.localize(datetime.combine(current.date() + timedelta(days=1), time.min))
        return current.astimezone(utc).replace(tzinfo=None)


class HelpdeskSlaHoliday(models.Model):
    _name = 'buz.helpdesk.sla.holiday'
    _description = 'Helpdesk SLA Holiday'
    _order = 'date'

    config_id = fields.Many2one(
        'buz.helpdesk.sla.config', required=True, ondelete='cascade',
    )
    date = fields.Date(required=True)
    name = fields.Char(required=True)

    _sql_constraints = [
        ('date_unique', 'unique(config_id, date)',
         'A holiday date can only be entered once.'),
    ]


class HelpdeskSlaRule(models.Model):
    _name = 'buz.helpdesk.sla.rule'
    _description = 'Helpdesk SLA Rule'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    config_id = fields.Many2one(
        'buz.helpdesk.sla.config', required=True, ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(related='config_id.company_id', store=True)
    category_id = fields.Many2one('buz.helpdesk.category')
    priority = fields.Selection([
        ('0', 'Low'), ('1', 'Normal'), ('2', 'High'), ('3', 'Urgent'),
    ])
    response_value = fields.Float(required=True, default=1.0)
    response_unit = fields.Selection([
        ('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'),
    ], required=True, default='hours')
    resolution_value = fields.Float(required=True, default=1.0)
    resolution_unit = fields.Selection([
        ('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'),
    ], required=True, default='hours')
    active = fields.Boolean(default=True)

    @api.constrains('response_value', 'resolution_value')
    def _check_values(self):
        for rule in self:
            if rule.response_value <= 0 or rule.resolution_value <= 0:
                raise ValidationError(_('SLA values must be greater than zero.'))

    def specificity(self):
        self.ensure_one()
        return bool(self.category_id) + bool(self.priority)

    def minutes(self, kind):
        self.ensure_one()
        value = getattr(self, '%s_value' % kind)
        unit = getattr(self, '%s_unit' % kind)
        return value * {'minutes': 1, 'hours': 60, 'days': 480}[unit]
