# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..engine import scheduler


class PlanScheduleLine(models.Model):
    _name = 'buz.plan.schedule.line'
    _description = 'Plan Schedule Line'
    _check_company_auto = True
    _order = 'workcenter_id, date_start, sequence, id'

    run_id = fields.Many2one('buz.plan.run', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(
        related='run_id.company_id', store=True, index=True, readonly=True)
    workorder_id = fields.Many2one(
        'mrp.workorder', required=True, index=True, ondelete='cascade', check_company=True)
    production_id = fields.Many2one(
        'mrp.production', related='workorder_id.production_id', store=True, index=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', required=True, index=True, check_company=True)
    product_id = fields.Many2one(
        'product.product', related='workorder_id.product_id', store=True)
    sequence = fields.Integer(default=10)
    date_start = fields.Datetime(required=True)
    date_end = fields.Datetime(required=True)
    duration_minutes = fields.Float()
    duration_source = fields.Selection(
        [('history', "History"), ('expected', "Expected")], default='expected')
    is_locked = fields.Boolean()
    is_late = fields.Boolean()
    is_manual = fields.Boolean()
    state = fields.Selection(
        [('proposed', "Proposed"), ('applied', "Applied")],
        default='proposed', required=True, index=True)

    _sql_constraints = [
        ('dates_ordered', 'check(date_end >= date_start)',
         "The end of a schedule line cannot be before its start."),
    ]

    def gantt_update(self, date_start, date_end, mode):
        """Drag (``move``) or stretch (``resize``) a bar from the Gantt.

        The result is snapped to working time of the workcenter calendar. The
        line becomes manual (kept by re-schedule) and goes back to proposed so
        that Apply writes it again.
        """
        self.ensure_one()
        if self.is_locked or self.workorder_id.state == 'progress':
            raise UserError(_("This job is locked (in progress or locked by a planner) and cannot be moved."))
        start = fields.Datetime.to_datetime(date_start)
        end = fields.Datetime.to_datetime(date_end)
        worktime = scheduler.CalendarWorkTime(self.env)
        wc = self.workcenter_id.id
        intervals = lambda a, b: worktime.intervals(wc, a, b)  # noqa: E731
        if mode == 'move':
            minutes = self.duration_minutes
        elif mode == 'resize':
            if end <= start:
                raise UserError(_("The end of a job must be after its start."))
            minutes = 0.0
            cursor = start
            while cursor < end:
                chunk_end = min(end, cursor + timedelta(days=14))
                minutes += sum((min(b, end) - max(a, cursor)).total_seconds() / 60.0
                               for a, b in intervals(cursor, chunk_end) if min(b, end) > max(a, cursor))
                cursor = chunk_end
            if minutes <= 0:
                raise UserError(_("That span contains no working time of workcenter %s.",
                                  self.workcenter_id.display_name))
        else:
            raise UserError(_("Unknown Gantt action %s.", mode))
        real_start, real_end = scheduler.consume(intervals, start, max(minutes, scheduler.MIN_MINUTES))
        deadline = self.production_id.date_deadline
        self.write({
            'date_start': real_start, 'date_end': real_end, 'duration_minutes': minutes,
            'is_manual': True, 'state': 'proposed',
            'is_late': bool(deadline and real_end > deadline),
        })
        return {'id': self.id, 'start': fields.Datetime.to_string(real_start),
                'end': fields.Datetime.to_string(real_end), 'minutes': round(minutes, 1)}
