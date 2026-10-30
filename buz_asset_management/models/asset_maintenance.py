# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

GUARDED = ('state', 'actual_start', 'actual_end', 'reminder_sent')
LOCKED_AFTER_DONE = ('asset_id', 'maintenance_type', 'planned_date', 'vendor_id', 'technician', 'description',
                     'result', 'cost', 'downtime_hours', 'warranty_covered', 'part_ids', 'recurrence_months')
REMINDER_LEAD_DAYS = 7


class BuzAssetMaintenance(models.Model):
    """Maintenance request / work log.

    Cost here is operational data. Nothing in this model touches the asset's
    cost, book value or any journal entry; capitalizing a repair is a separate
    approved accounting decision.
    """
    _name = 'buz.asset.maintenance'
    _description = 'งานบำรุงรักษาทรัพย์สิน'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'planned_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(readonly=True, copy=False, default='/', string='เลขที่')
    asset_id = fields.Many2one(
        'buz.asset', required=True, index=True, tracking=True, check_company=True,
        ondelete='restrict', string='ทรัพย์สิน')
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company, string='บริษัท')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True, string='สกุลเงิน')
    maintenance_type = fields.Selection([
        ('preventive', 'บำรุงรักษาเชิงป้องกัน'),
        ('corrective', 'ซ่อมแซม'),
        ('inspection', 'ตรวจสอบ'),
        ('calibration', 'สอบเทียบ'),
        ('other', 'อื่นๆ'),
    ], required=True, default='corrective', tracking=True, string='ประเภท')
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('planned', 'วางแผนแล้ว'),
        ('in_progress', 'กำลังดำเนินการ'),
        ('done', 'เสร็จสิ้น'),
        ('cancelled', 'ยกเลิก'),
    ], required=True, default='draft', copy=False, tracking=True, string='สถานะ')

    description = fields.Text(required=True, string='รายละเอียดงาน')
    result = fields.Text(string='ผลการดำเนินงาน')
    planned_date = fields.Date(tracking=True, string='วันที่วางแผน')
    actual_start = fields.Datetime(readonly=True, copy=False, string='เริ่มจริง')
    actual_end = fields.Datetime(readonly=True, copy=False, string='เสร็จจริง')
    responsible_id = fields.Many2one(
        'res.users', default=lambda self: self.env.user, tracking=True, string='ผู้รับผิดชอบ')
    vendor_id = fields.Many2one('res.partner', check_company=True, string='ผู้ให้บริการ')
    technician = fields.Char(string='ช่างผู้ดำเนินการ')
    warranty_covered = fields.Boolean(tracking=True, string='อยู่ในประกัน/รับประกัน')
    downtime_hours = fields.Float(string='เวลาหยุดใช้งาน (ชั่วโมง)')
    recurrence_months = fields.Integer(
        string='ทำซ้ำทุก (เดือน)', help="ถ้าระบุ ระบบจะสร้างกิจกรรมเตือนรอบถัดไปให้ผู้รับผิดชอบเมื่องานเสร็จ")
    reminder_sent = fields.Boolean(readonly=True, copy=False)

    cost = fields.Monetary(currency_field='currency_id', string='ค่าแรง/ค่าบริการ')
    part_ids = fields.One2many('buz.asset.maintenance.part', 'maintenance_id', string='อะไหล่')
    parts_cost = fields.Monetary(currency_field='currency_id', compute='_compute_total_cost', store=True,
                                 string='ค่าอะไหล่')
    total_cost = fields.Monetary(currency_field='currency_id', compute='_compute_total_cost', store=True,
                                 string='ค่าใช้จ่ายรวม')
    is_overdue = fields.Boolean(compute='_compute_is_overdue', search='_search_is_overdue', string='เลยกำหนด')

    _sql_constraints = [
        ('cost_non_negative', 'CHECK(cost >= 0)', 'ค่าใช้จ่ายต้องไม่ติดลบ'),
        ('downtime_non_negative', 'CHECK(downtime_hours >= 0)', 'เวลาหยุดใช้งานต้องไม่ติดลบ'),
        ('recurrence_non_negative', 'CHECK(recurrence_months >= 0)', 'รอบการทำซ้ำต้องไม่ติดลบ'),
    ]

    @api.depends('cost', 'part_ids.subtotal')
    def _compute_total_cost(self):
        for rec in self:
            rec.parts_cost = sum(rec.part_ids.mapped('subtotal'))
            rec.total_cost = rec.cost + rec.parts_cost

    @api.onchange('asset_id', 'planned_date')
    def _onchange_warranty_hint(self):
        """Suggest (never force) the warranty flag when a warranty covers the planned date."""
        if self.asset_id:
            date = self.planned_date or fields.Date.context_today(self)
            if self.asset_id._has_warranty_on(date):
                self.warranty_covered = True

    def _overdue_domain(self):
        return [('state', '=', 'planned'), ('planned_date', '<', fields.Date.context_today(self))]

    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_overdue = rec.state == 'planned' and bool(rec.planned_date) and rec.planned_date < today

    def _search_is_overdue(self, operator, value):
        if operator not in ('=', '!='):
            raise UserError(_("ตัวดำเนินการไม่รองรับ"))
        today = fields.Date.context_today(self)
        if (operator == '=') == bool(value):
            return [('state', '=', 'planned'), ('planned_date', '<', today)]
        return ['|', '|', ('state', '!=', 'planned'), ('planned_date', '=', False), ('planned_date', '>=', today)]

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.su and (any(k in vals for k in GUARDED if k != 'state')
                                    or vals.get('state', 'draft') != 'draft'):
                raise AccessError(_("ฟิลด์สถานะเปลี่ยนได้ผ่านขั้นตอนการทำงาน (workflow) เท่านั้น"))
            asset = self.env['buz.asset'].browse(vals['asset_id'])
            vals['company_id'] = asset.company_id.id
            vals['name'] = self.env['ir.sequence'].with_company(asset.company_id).next_by_code(
                'buz.asset.maintenance') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if any(k in vals for k in GUARDED):
                raise AccessError(_("ฟิลด์สถานะเปลี่ยนได้ผ่านขั้นตอนการทำงาน (workflow) เท่านั้น"))
            if any(rec.state in ('done', 'cancelled') for rec in self) and any(
                    k in vals for k in LOCKED_AFTER_DONE):
                raise UserError(_("งานที่เสร็จสิ้นหรือยกเลิกแล้วแก้ไขไม่ได้"))
            if 'asset_id' in vals and any(rec.state != 'draft' for rec in self):
                raise UserError(_("เปลี่ยนทรัพย์สินได้เฉพาะงานที่เป็นร่าง"))
        return super().write(vals)

    def unlink(self):
        if any(rec.state not in ('draft', 'cancelled') for rec in self):
            raise UserError(_("ลบได้เฉพาะงานที่เป็นร่างหรือยกเลิกแล้ว"))
        return super().unlink()

    # ------------------------------------------------------------------
    def _require_officer(self):
        if not self.env.user.has_group('buz_asset_management.group_asset_officer'):
            raise AccessError(_("คุณไม่มีสิทธิ์ทำรายการนี้"))

    def _require_state(self, *states):
        for rec in self:
            if rec.state not in states:
                raise UserError(_("งาน %(name)s ต้องอยู่ในสถานะ %(states)s", name=rec.name,
                                  states=', '.join(dict(self._fields['state'].selection)[s] for s in states)))

    def _check_asset_maintainable(self):
        for rec in self:
            asset = rec.asset_id
            if asset.operational_state == 'disposed' or asset.approval_state != 'approved':
                raise UserError(_("ทรัพย์สิน %s ต้องอนุมัติแล้วและยังไม่ถูกจำหน่าย", asset.display_name))

    def _sync_asset_state(self, assets):
        """under_maintenance while any job is in progress; restore in_service afterwards."""
        for asset in assets:
            busy = self.search_count([('asset_id', '=', asset.id), ('state', '=', 'in_progress')])
            if busy and asset.operational_state == 'in_service':
                asset.sudo().write({'operational_state': 'under_maintenance'})  # sudo: state write guard
            elif not busy and asset.operational_state == 'under_maintenance':
                asset.sudo().write({'operational_state': 'in_service'})  # sudo: state write guard

    def action_plan(self):
        self._require_officer()
        self._require_state('draft')
        self._check_asset_maintainable()
        for rec in self:
            if not rec.planned_date:
                raise UserError(_("กรุณาระบุวันที่วางแผนของงาน %s", rec.name))
        self.sudo().write({'state': 'planned'})  # sudo: state guard; group checked above

    def action_start(self):
        self._require_officer()
        self._require_state('draft', 'planned')
        self._check_asset_maintainable()
        self.sudo().write({'state': 'in_progress', 'actual_start': fields.Datetime.now()})  # sudo: state guard
        self._sync_asset_state(self.asset_id)

    def action_done(self):
        self._require_officer()
        self._require_state('in_progress')
        now = fields.Datetime.now()
        for rec in self:
            if not (rec.result or '').strip():
                raise UserError(_("กรุณาระบุผลการดำเนินงานของ %s ก่อนปิดงาน", rec.name))
            vals = {'state': 'done', 'actual_end': now}
            if not rec.downtime_hours and rec.actual_start:
                vals['downtime_hours'] = round((now - rec.actual_start).total_seconds() / 3600.0, 2)
            rec.sudo().write(vals)  # sudo: state guard; group checked above
            if rec.recurrence_months and rec.responsible_id:
                due = fields.Date.context_today(rec) + relativedelta(months=rec.recurrence_months)
                rec.activity_schedule(
                    'mail.mail_activity_data_todo', date_deadline=due, user_id=rec.responsible_id.id,
                    summary=_("บำรุงรักษารอบถัดไป: %s", rec.asset_id.display_name))
        self._sync_asset_state(self.asset_id)

    def action_cancel(self):
        self._require_officer()
        self._require_state('draft', 'planned', 'in_progress')
        self.sudo().write({'state': 'cancelled'})  # sudo: state guard; group checked above
        self._sync_asset_state(self.asset_id)

    def action_reset_to_draft(self):
        self._require_officer()
        self._require_state('cancelled')
        self.sudo().write({'state': 'draft', 'actual_start': False, 'reminder_sent': False})  # sudo: state guard

    # ------------------------------------------------------------------
    @api.model
    def _cron_remind_due(self, batch_size=200):
        """One reminder activity per planned job entering its lead window; safe to rerun."""
        limit = fields.Date.context_today(self) + relativedelta(days=REMINDER_LEAD_DAYS)
        jobs = self.search([('state', '=', 'planned'), ('reminder_sent', '=', False),
                            ('planned_date', '<=', limit), ('responsible_id', '!=', False)], limit=batch_size)
        for job in jobs:
            with self.env.cr.savepoint():
                job.activity_schedule(
                    'mail.mail_activity_data_todo', date_deadline=job.planned_date, user_id=job.responsible_id.id,
                    summary=_("งานบำรุงรักษาใกล้ถึงกำหนด: %s", job.asset_id.display_name))
                job.sudo().write({'reminder_sent': True})


class BuzAssetMaintenancePart(models.Model):
    _name = 'buz.asset.maintenance.part'
    _description = 'อะไหล่งานบำรุงรักษา'

    maintenance_id = fields.Many2one('buz.asset.maintenance', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', related='maintenance_id.company_id', store=True, index=True)
    currency_id = fields.Many2one('res.currency', related='maintenance_id.currency_id')
    name = fields.Char(required=True, string='อะไหล่')
    quantity = fields.Float(default=1.0, string='จำนวน')
    unit_cost = fields.Monetary(currency_field='currency_id', string='ราคาต่อหน่วย')
    subtotal = fields.Monetary(currency_field='currency_id', compute='_compute_subtotal', store=True,
                               string='รวม')

    _sql_constraints = [
        ('quantity_positive', 'CHECK(quantity > 0)', 'จำนวนอะไหล่ต้องมากกว่าศูนย์'),
        ('unit_cost_non_negative', 'CHECK(unit_cost >= 0)', 'ราคาอะไหล่ต้องไม่ติดลบ'),
    ]

    @api.depends('quantity', 'unit_cost')
    def _compute_subtotal(self):
        for part in self:
            part.subtotal = part.currency_id.round(part.quantity * part.unit_cost) if part.currency_id else (
                part.quantity * part.unit_cost)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            for vals in vals_list:
                parent = self.env['buz.asset.maintenance'].browse(vals.get('maintenance_id'))
                if parent.state in ('done', 'cancelled'):
                    raise UserError(_("งานที่เสร็จสิ้นหรือยกเลิกแล้วแก้ไขอะไหล่ไม่ได้"))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and any(p.maintenance_id.state in ('done', 'cancelled') for p in self):
            raise UserError(_("งานที่เสร็จสิ้นหรือยกเลิกแล้วแก้ไขอะไหล่ไม่ได้"))
        return super().write(vals)

    def unlink(self):
        if not self.env.su and any(p.maintenance_id.state in ('done', 'cancelled') for p in self):
            raise UserError(_("งานที่เสร็จสิ้นหรือยกเลิกแล้วแก้ไขอะไหล่ไม่ได้"))
        return super().unlink()
