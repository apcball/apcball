# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
# pylint: disable=protected-access  # standard ORM helpers (_read_group, _bom_find, _for_xml_id, ...)
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..engine import gantt, scheduler
from ..engine.mrp_netting import PlanGatherer, persist, solve
from .res_config_settings import get_plan_config


class PlanRun(models.Model):
    _name = 'buz.plan.run'
    _description = 'Production Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'id desc'

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _("New"))
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    user_id = fields.Many2one(
        'res.users', string="Planner", required=True, default=lambda self: self.env.user,
        tracking=True)
    date_from = fields.Date(
        required=True, default=fields.Date.context_today, tracking=True,
        help="Start of the first weekly bucket (Monday of this date's week).")
    horizon_weeks = fields.Integer(
        required=True, default=lambda self: get_plan_config(self.env)['horizon_weeks'])
    date_to = fields.Date(compute='_compute_date_to', store=True)
    warehouse_ids = fields.Many2many(
        'stock.warehouse', string="Supply Warehouses", check_company=True,
        default=lambda self: self._default_warehouse_ids())
    picking_type_ids = fields.Many2many(
        'stock.picking.type', string="Production Lines", check_company=True,
        domain=[('code', '=', 'mrp_operation')],
        help="Limit the plan to these production lines. Empty = all.")
    forecast_lookback_weeks = fields.Integer(
        required=True, default=lambda self: get_plan_config(self.env)['lookback_weeks'])
    state = fields.Selection([
        ('draft', "Draft"),
        ('computed', "Computed"),
        ('confirmed', "Confirmed"),
        ('done', "Done"),
        ('cancel', "Cancelled"),
    ], default='draft', required=True, copy=False, tracking=True)
    demand_line_ids = fields.One2many('buz.plan.demand.line', 'run_id')
    suggestion_ids = fields.One2many('buz.plan.suggestion', 'run_id')
    schedule_line_ids = fields.One2many('buz.plan.schedule.line', 'run_id')
    suggestion_count = fields.Integer(compute='_compute_counts')
    schedule_count = fields.Integer(compute='_compute_counts')

    _sql_constraints = [
        ('horizon_positive', 'check(horizon_weeks > 0)', "Horizon must be at least 1 week."),
        ('lookback_positive', 'check(forecast_lookback_weeks >= 0)',
         "Forecast look-back cannot be negative."),
    ]

    @api.model
    def _default_warehouse_ids(self):
        codes = get_plan_config(self.env)['warehouse_codes']
        return self.env['stock.warehouse'].search([
            ('code', 'in', codes), ('company_id', '=', self.env.company.id)]).ids

    @api.depends('date_from', 'horizon_weeks')
    def _compute_date_to(self):
        for run in self:
            if run.date_from:
                monday = run.date_from - timedelta(days=run.date_from.weekday())
                run.date_to = monday + timedelta(weeks=run.horizon_weeks, days=-1)
            else:
                run.date_to = False

    @api.depends('suggestion_ids', 'schedule_line_ids')
    def _compute_counts(self):
        for run in self:
            run.suggestion_count = len(run.suggestion_ids)
            run.schedule_count = len(run.schedule_line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _("New"):
                vals['name'] = self.env['ir.sequence'].next_by_code('buz.plan.run') or _("New")
        return super().create(vals_list)

    def action_compute(self):
        """Compute demand lines and make/buy suggestions (batch, no per-product queries)."""
        cfg = get_plan_config(self.env)
        for run in self:
            # Confirmed = some documents already created; they are kept and deducted.
            if run.state not in ('draft', 'computed', 'confirmed'):
                raise UserError(_(
                    "Plan %s can only be computed while it is Draft, Computed or Confirmed.",
                    run.name))
            if not run.warehouse_ids:
                raise UserError(_(
                    "Select at least one supply warehouse on plan %s before computing.", run.name))
            data = PlanGatherer(run).gather(cfg)
            result = solve(data)
            n_sugg, n_dem = persist(run, result)
            run.state = 'computed'
            body = Markup("%s<br/>%s") % (
                _("Computed: %(s)s suggestions, %(d)s demand lines, %(p)s products planned.",
                  s=n_sugg, d=n_dem, p=len(data.products)),
                Markup("<br/>").join(result.warnings[:50]))
            run.message_post(body=body)
        return True

    def action_schedule(self):
        """Place open workorders on their workcenters. Writes schedule lines only."""
        cfg = get_plan_config(self.env)
        for run in self:
            if run.state == 'cancel':
                raise UserError(_("Plan %s is cancelled.", run.name))
            stats = scheduler.run_schedule(run, cfg)
            run.message_post(body=_(
                "Scheduled %(wo)s workorders of %(mo)s manufacturing orders: %(late)s late, "
                "%(locked)s fixed (in progress, locked or manually placed).",
                wo=stats['workorders'], mo=stats['productions'],
                late=stats['late'], locked=stats['locked']))
        return True

    def apply_schedule_batch(self, limit=scheduler.APPLY_BATCH_MOS):
        """Apply the next ``limit`` manufacturing orders (Planning / Manager).

        Returns ``{'applied', 'skipped', 'remaining'}`` so a client can loop
        with a progress message. Each call is its own transaction and can be
        repeated safely.
        """
        self.ensure_one()
        if not self.env.user.has_group('buz_production_planning.group_plan_manager'):
            raise AccessError(_("Only Planning / Manager can apply a schedule to workorders."))
        lines = self.schedule_line_ids.filtered(lambda l: l.state == 'proposed')
        if not lines:
            raise UserError(_("Nothing to apply: schedule plan %s first.", self.name))
        done, skipped, remaining = scheduler.apply_lines(lines, limit)
        self.message_post(body=_(
            "Applied %(done)s workorder dates. Skipped %(skip)s (in progress, no longer open, or "
            "their manufacturing order already has done stock moves). "
            "%(left)s manufacturing orders still to apply.",
            done=len(done), skip=len(skipped), left=remaining))
        return {'applied': len(done), 'skipped': len(skipped), 'remaining': remaining}

    def action_apply_schedule(self):
        """Form button: apply one batch and say whether to press again."""
        self.ensure_one()
        res = self.apply_schedule_batch()
        message = _("Applied %s workorder dates.", res['applied'])
        if res['remaining']:
            message = _("%(msg)s %(left)s manufacturing orders remain: click Apply Schedule again.",
                        msg=message, left=res['remaining'])
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _("Schedule applied"), 'message': message,
                       'type': 'warning' if res['remaining'] else 'success', 'sticky': bool(res['remaining'])},
        }

    def action_open_gantt(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client', 'tag': 'buz_production_planning.gantt',
            'name': _("Schedule Gantt"), 'params': {'run_id': self.id},
        }

    @api.model
    def gantt_data(self, run_id=False, date_from=False, date_to=False, tz=None, filters=None):
        """Everything the Gantt needs for the visible window, as plain JSON."""
        filters = filters or {}
        tz = tz or self.env.user.tz or 'Asia/Bangkok'
        runs = self.search(
            [('state', '!=', 'cancel'), ('schedule_line_ids', '!=', False)], order='id desc', limit=30)
        run = self.browse(run_id) if run_id else runs[:1]
        res = {
            'runs': [{'id': r.id, 'name': r.name} for r in runs], 'run': False,
            'workcenters': [], 'lines': [], 'capacity': {}, 'load': {}, 'picking_types': [],
            'can_apply': self.env.user.has_group('buz_production_planning.group_plan_manager'),
        }
        if not run:
            return res
        run.check_access_rule('read')
        all_lines = run.schedule_line_ids
        res['run'] = {'id': run.id, 'name': run.name, 'state': run.state}
        res['picking_types'] = [
            {'id': p.id, 'name': p.display_name} for p in all_lines.production_id.picking_type_id]
        lines = all_lines
        if filters.get('picking_type_id'):
            lines = lines.filtered(lambda l: l.production_id.picking_type_id.id == filters['picking_type_id'])
        if filters.get('late_only'):
            lines = lines.filtered('is_late')
        wcs = all_lines.workcenter_id
        if filters.get('workcenter_id'):
            wcs = wcs.filtered(lambda w: w.id == filters['workcenter_id'])
        wcs = wcs.sorted(key=lambda w: (gantt.wc_group(w)[0], w.code or '', w.name))
        res['workcenters'] = [{
            'id': w.id, 'name': w.name, 'code': w.code or '',
            'group': gantt.wc_group(w)[1],
        } for w in wcs]
        d0 = (fields.Datetime.to_datetime(date_from) if date_from
              else min(lines.mapped('date_start'), default=fields.Datetime.now()))
        d1 = fields.Datetime.to_datetime(date_to) if date_to else d0 + timedelta(days=14)
        visible = lines.filtered(
            lambda l: l.workcenter_id in wcs and l.date_end >= d0 and l.date_start <= d1)
        for l in visible:
            wo, mo = l.workorder_id, l.production_id
            res['lines'].append({
                'id': l.id, 'wc': l.workcenter_id.id, 'mo_id': mo.id, 'mo': mo.name,
                'product': mo.product_id.display_name, 'qty': wo.qty_production,
                'operation': wo.name,
                'start': fields.Datetime.to_string(l.date_start),
                'end': fields.Datetime.to_string(l.date_end),
                'deadline': fields.Datetime.to_string(mo.date_deadline) if mo.date_deadline else False,
                'minutes': round(l.duration_minutes, 1), 'source': l.duration_source,
                'is_late': l.is_late, 'is_locked': l.is_locked or wo.state == 'progress',
                'is_manual': l.is_manual, 'state': l.state,
            })
        worktime = scheduler.CalendarWorkTime(self.env)
        res['capacity'], res['load'] = gantt.capacity_and_load(worktime, wcs, visible, d0, d1, tz)
        return res

    def action_cancel(self):
        if any(run.state == 'done' for run in self):
            raise UserError(_("A plan that is done cannot be cancelled."))
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.filtered(lambda r: r.state == 'cancel').write({'state': 'draft'})

    def action_open_suggestions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'buz_production_planning.action_buz_plan_suggestion')
        action['domain'] = [('run_id', '=', self.id)]
        action['context'] = {'default_run_id': self.id}
        return action

    def action_open_schedule(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'buz_production_planning.action_buz_plan_schedule_line')
        action['domain'] = [('run_id', '=', self.id)]
        action['context'] = {'default_run_id': self.id}
        return action
