# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.osv import expression


class BuzAssetCoverage(models.Model):
    """Warranty or insurance record of an asset. Tracking only: no accounting
    entries are created for premiums or claims in the MVP."""
    _name = 'buz.asset.coverage'
    _description = 'การรับประกัน/ประกันภัยทรัพย์สิน'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end, id'
    _check_company_auto = True
    _rec_name = 'reference'

    asset_id = fields.Many2one(
        'buz.asset', required=True, index=True, ondelete='cascade', tracking=True, check_company=True,
        string='ทรัพย์สิน')
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company, string='บริษัท')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True, string='สกุลเงิน')
    active = fields.Boolean(default=True, string='เปิดใช้งาน')
    coverage_type = fields.Selection([
        ('warranty', 'การรับประกัน'),
        ('insurance', 'ประกันภัย'),
    ], required=True, default='warranty', tracking=True, string='ประเภท')
    provider_id = fields.Many2one('res.partner', check_company=True, tracking=True, string='ผู้ให้บริการ/บริษัทประกัน')
    reference = fields.Char(required=True, tracking=True, string='เลขที่การรับประกัน/เลขที่กรมธรรม์')
    date_start = fields.Date(required=True, tracking=True, string='วันที่เริ่ม')
    date_end = fields.Date(required=True, tracking=True, string='วันที่สิ้นสุด')
    coverage = fields.Text(string='ความคุ้มครอง')
    terms = fields.Text(string='เงื่อนไข')
    insured_amount = fields.Monetary(currency_field='currency_id', string='ทุนประกัน')
    responsible_id = fields.Many2one(
        'res.users', default=lambda self: self.env.user, tracking=True, string='ผู้รับผิดชอบการติดตาม')
    reminder_days = fields.Integer(default=30, string='เตือนล่วงหน้า (วัน)')
    reminder_sent = fields.Boolean(readonly=True, copy=False, string='ส่งการเตือนแล้ว')
    state = fields.Selection([
        ('upcoming', 'ยังไม่เริ่ม'),
        ('active', 'มีผลอยู่'),
        ('expiring', 'ใกล้หมดอายุ'),
        ('expired', 'หมดอายุ'),
    ], compute='_compute_state', search='_search_state', string='สถานะ')
    days_left = fields.Integer(compute='_compute_state', string='เหลืออีก (วัน)')

    _sql_constraints = [
        ('dates_ordered', 'CHECK(date_end >= date_start)', 'วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่ม'),
        ('insured_non_negative', 'CHECK(insured_amount >= 0)', 'ทุนประกันต้องไม่ติดลบ'),
        ('reminder_non_negative', 'CHECK(reminder_days >= 0)', 'จำนวนวันเตือนต้องไม่ติดลบ'),
    ]

    @api.depends('date_start', 'date_end', 'reminder_days')
    @api.depends_context('uid')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.date_start or not rec.date_end:
                rec.state, rec.days_left = 'active', 0
                continue
            rec.days_left = (rec.date_end - today).days
            if today < rec.date_start:
                rec.state = 'upcoming'
            elif today > rec.date_end:
                rec.state = 'expired'
            elif rec.days_left <= rec.reminder_days:
                rec.state = 'expiring'
            else:
                rec.state = 'active'

    def _search_state(self, operator, value):
        if operator not in ('=', 'in'):
            raise UserError(_("ตัวดำเนินการไม่รองรับ"))
        values = [value] if operator == '=' else list(value)
        today = fields.Date.context_today(self)
        # expiring is "in force" with end date inside the record's own reminder window; resolve it in Python.
        in_force = self.search([('date_start', '<=', today), ('date_end', '>=', today)])
        expiring_ids = in_force.filtered(lambda r: (r.date_end - today).days <= r.reminder_days).ids
        clauses = []
        if 'upcoming' in values:
            clauses.append([('date_start', '>', today)])
        if 'expired' in values:
            clauses.append([('date_end', '<', today)])
        if 'expiring' in values:
            clauses.append([('id', 'in', expiring_ids)])
        if 'active' in values:
            clauses.append([('id', 'in', in_force.ids), ('id', 'not in', expiring_ids)])
        if not clauses:
            return [('id', '=', 0)]
        return expression.OR(clauses)

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.su and 'reminder_sent' in vals:
                raise AccessError(_("ฟิลด์นี้เปลี่ยนได้โดยระบบเท่านั้น"))
            if vals.get('asset_id'):
                vals['company_id'] = self.env['buz.asset'].browse(vals['asset_id']).company_id.id
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and 'reminder_sent' in vals:
            raise AccessError(_("ฟิลด์นี้เปลี่ยนได้โดยระบบเท่านั้น"))
        if {'date_end', 'reminder_days'} & set(vals):
            vals = dict(vals, reminder_sent=False)  # a renewed/changed window earns a new reminder
        if 'asset_id' in vals and not self.env.su:
            raise UserError(_("เปลี่ยนทรัพย์สินไม่ได้ กรุณาสร้างรายการใหม่"))
        return super().write(vals)

    @api.model
    def _cron_remind_expiring(self, batch_size=200):
        """One reminder per record entering its window; rerun-safe, batch-limited."""
        today = fields.Date.context_today(self)
        candidates = self.search([
            ('reminder_sent', '=', False), ('date_end', '>=', today), ('date_start', '<=', today)],
            order='date_end', limit=batch_size * 3)
        due = candidates.filtered(lambda r: (r.date_end - today).days <= r.reminder_days)[:batch_size]
        for rec in due:
            with self.env.cr.savepoint():
                label = dict(self._fields['coverage_type'].selection)[rec.coverage_type]
                summary = _("%(type)s ใกล้หมดอายุ: %(asset)s (%(ref)s) สิ้นสุด %(end)s",
                            type=label, asset=rec.asset_id.display_name, ref=rec.reference, end=rec.date_end)
                if rec.responsible_id:
                    rec.activity_schedule('mail.mail_activity_data_todo', date_deadline=rec.date_end,
                                          user_id=rec.responsible_id.id, summary=summary)
                else:
                    # No owner to notify: leave a visible trace instead of skipping silently.
                    rec.message_post(body=summary)
                rec.sudo().write({'reminder_sent': True})
