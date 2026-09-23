from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from .bsf_cost import require_manager
from .bsf_cost_math import finite_nonnegative, normalized_savings

FINANCE_GROUPS = 'biz_smart_finance.group_bsf_user'
DOMAINS = [('cash', 'สภาพคล่อง'), ('ar', 'ลูกหนี้/ยอดขายสู่เงินสด'), ('ap', 'เจ้าหนี้'),
           ('margin', 'กำไรโครงการ'), ('budget', 'งบประมาณ'), ('inventory', 'สินค้าคงคลัง'),
           ('channel', 'ช่องทางขาย'), ('capital', 'เงินทุน'), ('risk', 'ความเสี่ยง'),
           ('cost', 'ต้นทุน/จุดคุ้มทุน'), ('personnel', 'บุคลากร')]
PLAYBOOKS = {
    'cash': 'ทบทวนช่วงเงินขาด เร่งเงินรับที่ยืนยันได้ และจัดทางเลือกเงินทุน',
    'ar': 'ตรวจเอกสารค้างวางบิล ยืนยันวันรับเงิน และเชื่อมงานติดตามหนี้เดิม',
    'ap': 'จัดลำดับจ่ายตามวันครบกำหนดและความสำคัญคู่ค้า เตรียมเจรจาเงื่อนไข',
    'margin': 'ทบทวนต้นทุนคงเหลือ ขอบเขตงาน และงานเพิ่มที่ยังไม่อนุมัติ',
    'budget': 'ตรวจภาระผูกพัน ลดหรือเลื่อนค่าใช้จ่าย และเสนอปรับงบพร้อมเหตุผล',
    'inventory': 'ทบทวนแผนซื้อ การใช้ และการระบายสต็อกตามข้อมูลที่มี',
    'channel': 'ทบทวนราคา ส่วนลด และส่วนผสมสินค้าที่สร้างกำไรส่วนเกิน',
    'capital': 'ทบทวนหนี้ วงเงิน และต้นทุนเงินทุนพร้อมวันครบกำหนด',
    'risk': 'ยืนยันสาเหตุและปรับแผนรับมือกับเจ้าของความเสี่ยง',
    'cost': 'เปรียบเทียบเพิ่มยอดขาย ปรับส่วนลด ลดของเสีย เจรจาค่าเช่า และยกเลิกบริการซ้ำซ้อน',
    'personnel': 'ตรวจภาระงานและ OT จัดตารางและใช้กำลังคนร่วมกัน ทบทวนตำแหน่งว่าง โดยประเมินคุณภาพและกำลังบริการ',
}


class Strategy(models.Model):
    _name = 'biz.smart.finance.strategy'
    _description = 'แผนกลยุทธ์การเงินรายปี'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    name = fields.Char(required=True, tracking=True, string='กลยุทธ์')
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    owner_id = fields.Many2one('res.users', required=True, default=lambda s: s.env.user, string='เจ้าของแผน')
    date_start = fields.Date(required=True, string='เริ่มปีงบ')
    date_end = fields.Date(required=True, string='สิ้นปีงบ')
    objective = fields.Text(string='เป้าหมายเชิงกลยุทธ์')
    goal_ids = fields.One2many('biz.smart.finance.goal', 'strategy_id', string='KPI / เป้ารายไตรมาส')
    review_ids = fields.One2many('biz.smart.finance.strategy.review', 'strategy_id', string='ทบทวนรายเดือน')
    state = fields.Selection([('draft', 'ร่าง'), ('active', 'ใช้งาน'), ('closed', 'ปิดแผน')], default='draft', tracking=True)

    @api.onchange('company_id')
    def _onchange_company(self):
        if self.company_id:
            dates = self.company_id.compute_fiscalyear_dates(fields.Date.context_today(self))
            self.date_start, self.date_end = dates['date_from'], dates['date_to']

    @api.constrains('date_start', 'date_end', 'owner_id', 'company_id')
    def _check_dates(self):
        for rec in self:
            if rec.date_start > rec.date_end or rec.company_id not in rec.owner_id.company_ids:
                raise ValidationError(_('ตรวจช่วงวันที่และบริษัทของเจ้าของแผน'))


class Goal(models.Model):
    _name = 'biz.smart.finance.goal'
    _description = 'เป้าหมาย KPI รายไตรมาส'
    _check_company_auto = True
    name = fields.Char(required=True, string='KPI')
    strategy_id = fields.Many2one('biz.smart.finance.strategy', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='strategy_id.company_id', store=True)
    quarter = fields.Selection([(str(i), 'Q%s' % i) for i in range(1, 5)], required=True, default='1')
    category = fields.Selection(DOMAINS, required=True, default='cost')
    owner_id = fields.Many2one('res.users', required=True, default=lambda s: s.env.user)
    baseline = fields.Float(string='ค่าฐาน')
    target = fields.Float(string='เป้า')
    actual = fields.Float(string='ผลล่าสุด')
    unit = fields.Selection([('money', 'สกุลเงินบริษัท'), ('pct', '%'), ('days', 'วัน'), ('ratio', 'เท่า'), ('number', 'จำนวน')], required=True, default='money')
    direction = fields.Selection([('up', 'สูงขึ้นดี'), ('down', 'ต่ำลงดี')], required=True, default='up')
    due_date = fields.Date(required=True, string='กำหนดเสร็จ')
    evidence = fields.Text(string='หลักฐานค่าจริง/วันที่วัด')
    progress_pct = fields.Float(compute='_compute_progress')

    @api.depends('baseline', 'target', 'actual')
    def _compute_progress(self):
        for rec in self:
            gap = rec.target - rec.baseline
            rec.progress_pct = (rec.actual - rec.baseline) / gap * 100 if gap else 0

    @api.constrains('due_date', 'strategy_id', 'owner_id', 'baseline', 'target', 'actual')
    def _check_goal(self):
        import math
        for rec in self:
            if not rec.strategy_id.date_start <= rec.due_date <= rec.strategy_id.date_end:
                raise ValidationError(_('กำหนด KPI ต้องอยู่ในปีของแผน'))
            if rec.company_id not in rec.owner_id.company_ids or not all(math.isfinite(rec[k]) for k in ('baseline', 'target', 'actual')):
                raise ValidationError(_('ผู้รับผิดชอบหรือค่าของ KPI ไม่ถูกต้อง'))


class StrategyReview(models.Model):
    _name = 'biz.smart.finance.strategy.review'
    _description = 'ทบทวนกลยุทธ์รายเดือน'
    strategy_id = fields.Many2one('biz.smart.finance.strategy', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='strategy_id.company_id', store=True)
    month = fields.Date(required=True, string='เดือนที่ทบทวน')
    name = fields.Char(required=True, string='ข้อสรุป')
    evidence = fields.Text(required=True, string='KPI / หลักฐาน')
    decisions = fields.Text(string='ข้อสั่งการ / ปรับแผน')
    reviewer_id = fields.Many2one('res.users', default=lambda s: s.env.user, required=True)
    _sql_constraints = [('monthly_review', 'unique(strategy_id, month)', 'มีการทบทวนเดือนนี้แล้ว')]

    @api.constrains('month', 'strategy_id')
    def _check_month(self):
        for rec in self:
            if rec.month.day != 1 or not rec.strategy_id.date_start.replace(day=1) <= rec.month <= rec.strategy_id.date_end:
                raise ValidationError(_('ระบุวันที่ 1 ของเดือนภายในปีแผน'))


class Issue(models.Model):
    _name = 'biz.smart.finance.issue'
    _description = 'ประเด็นการเงินและหลักฐาน'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'priority desc, financial_impact desc, id desc'
    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    month = fields.Date(required=True, default=lambda s: fields.Date.context_today(s).replace(day=1))
    category = fields.Selection(DOMAINS, required=True, default='cost')
    source_key = fields.Char(index=True, copy=False)
    evidence = fields.Text(required=True, string='หลักฐานและเกณฑ์')
    suspected_cause = fields.Text(string='สาเหตุที่ต้องตรวจสอบ')
    confirmed_cause = fields.Text(string='สาเหตุที่ยืนยันแล้ว', tracking=True)
    recommendation = fields.Text(string='แม่แบบ Action')
    financial_impact = fields.Monetary(string='มูลค่าที่เกี่ยวข้อง (ไม่ใช่ผลประหยัด)')
    priority = fields.Selection([('1', 'ติดตาม'), ('2', 'สำคัญ'), ('3', 'เร่งด่วน')], default='2', required=True)
    state = fields.Selection([('open', 'เปิด'), ('monitor', 'ติดตามผล'), ('closed', 'ปิด')], default='open', tracking=True)
    observed_at = fields.Datetime(readonly=True)
    risk_id = fields.Many2one('biz.smart.finance.risk', check_company=True)
    followup_id = fields.Many2one('biz.smart.finance.collection.followup', check_company=True)
    goal_id = fields.Many2one('biz.smart.finance.goal', check_company=True)
    action_ids = fields.One2many('biz.smart.finance.action', 'issue_id')
    _sql_constraints = [('issue_source', 'unique(company_id, month, source_key)', 'ประเด็นต้นทางนี้มีแล้วในงวด')]

    def action_create_action(self):
        require_manager(self.env)
        self.ensure_one()
        existing = self.action_ids.filtered(lambda a: a.state != 'cancelled')[:1]
        action = existing or self.env['biz.smart.finance.action'].create({
            'name': self.name, 'company_id': self.company_id.id, 'issue_id': self.id,
            'goal_id': self.goal_id.id, 'instructions': self.recommendation or PLAYBOOKS[self.category],
            'shared_evidence': '', 'category': self.category,
        })
        return {'type': 'ir.actions.act_window', 'res_model': action._name, 'res_id': action.id,
                'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}


class FinanceAction(models.Model):
    _name = 'biz.smart.finance.action'
    _description = 'แผนปฏิบัติการ CFO'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'due_date, priority desc, id desc'
    name = fields.Char(required=True, tracking=True, string='Action')
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    category = fields.Selection(DOMAINS, required=True, default='cost')
    owner_id = fields.Many2one('res.users', required=True, default=lambda s: s.env.user, tracking=True, string='ผู้รับงาน')
    due_date = fields.Date(string='กำหนดเสร็จ', tracking=True)
    priority = fields.Selection([('1', 'ติดตาม'), ('2', 'สำคัญ'), ('3', 'เร่งด่วน')], default='2')
    instructions = fields.Text(string='ขั้นตอนปฏิบัติ / KPI และเป้าหมาย', required=True)
    shared_evidence = fields.Text(string='ข้อมูลที่เลือกเปิดให้ผู้รับงาน')
    issue_id = fields.Many2one('biz.smart.finance.issue', check_company=True, groups=FINANCE_GROUPS)
    goal_id = fields.Many2one('biz.smart.finance.goal', check_company=True, groups=FINANCE_GROUPS)
    risk_id = fields.Many2one('biz.smart.finance.risk', check_company=True, groups=FINANCE_GROUPS)
    followup_id = fields.Many2one('biz.smart.finance.collection.followup', check_company=True, groups=FINANCE_GROUPS)
    expected_saving = fields.Monetary(string='ผลประหยัดคาดการณ์', groups=FINANCE_GROUPS)
    implementation_cost = fields.Monetary(string='ต้นทุนดำเนินการ', groups=FINANCE_GROUPS)
    progress = fields.Float(string='ความคืบหน้า (%)', tracking=True)
    blocked = fields.Boolean(string='ติดขัด', tracking=True)
    progress_note = fields.Text(string='บันทึกความคืบหน้า', tracking=True)
    result_evidence = fields.Text(string='หลักฐานส่งตรวจผล', tracking=True)
    overdue = fields.Boolean(compute='_compute_overdue', string='เกินกำหนด')
    state = fields.Selection([('draft', 'ร่าง'), ('review', 'รออนุมัติ'), ('approved', 'อนุมัติ'),
                              ('doing', 'กำลังทำ'), ('verify', 'รอตรวจผล'), ('done', 'ปิดงาน'),
                              ('cancelled', 'ยกเลิก')], required=True, default='draft', tracking=True, copy=False)
    plan_revision = fields.Integer(default=1, readonly=True, copy=False, string='ฉบับแผน')
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    verified_by = fields.Many2one('res.users', readonly=True, copy=False)
    review_ids = fields.One2many('biz.smart.finance.action.review', 'action_id', groups=FINANCE_GROUPS)
    verified_saving = fields.Monetary(compute='_compute_verified', groups=FINANCE_GROUPS, string='ผลประหยัดตรวจรับแล้ว')

    @api.depends('review_ids.accepted_saving', 'review_ids.verified')
    def _compute_verified(self):
        for rec in self:
            rec.verified_saving = sum(rec.review_ids.filtered('verified').mapped('accepted_saving'))

    @api.depends('due_date', 'state')
    def _compute_overdue(self):
        for rec in self:
            rec.overdue = bool(rec.due_date and rec.due_date < fields.Date.context_today(rec) and rec.state not in ('done', 'cancelled'))

    @api.constrains('owner_id', 'company_id', 'progress')
    def _check_action(self):
        for rec in self:
            if rec.company_id not in rec.owner_id.company_ids:
                raise ValidationError(_('ผู้รับงานต้องมีสิทธิ์บริษัทนี้'))
            if not finite_nonnegative(rec.progress) or rec.progress > 100:
                raise ValidationError(_('ตรวจจำนวนเงินและความคืบหน้า 0–100%'))

    @api.constrains('expected_saving', 'implementation_cost')
    def _check_amounts(self):
        for rec in self:
            if not finite_nonnegative(rec.expected_saving, rec.implementation_cost):
                raise ValidationError(_('จำนวนเงินต้องไม่ติดลบ'))

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        for vals in vals_list:
            if vals.get('state', self.env.context.get('default_state', 'draft')) != 'draft' or any(k in vals or ('default_' + k) in self.env.context for k in ('approved_by', 'verified_by', 'plan_revision')):
                raise AccessError(_('ต้องเริ่มจากร่าง'))
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) & {'state', 'approved_by', 'verified_by', 'plan_revision'}:
            raise AccessError(_('เปลี่ยนสถานะผ่านปุ่มดำเนินงานเท่านั้น'))
        progress_fields = {'progress', 'blocked', 'progress_note', 'result_evidence'}
        technical = {'message_follower_ids', 'activity_ids', 'message_main_attachment_id'}
        manager = self.env.su or self.env.user.has_group('biz_smart_finance.group_bsf_manager')
        if not manager:
            if set(vals) - progress_fields or any(a.owner_id != self.env.user or a.state not in ('approved', 'doing', 'verify') for a in self):
                raise AccessError(_('แก้ได้เฉพาะความคืบหน้าและหลักฐานงานที่ได้รับ'))
        if any(a.state in ('done', 'cancelled') for a in self) and set(vals) - technical:
            raise UserError(_('งานปิดแล้ว ต้องเปิดทบทวนก่อน'))
        changed_plan = bool(set(vals) - progress_fields - technical)
        result = super().write(vals)
        if changed_plan:
            approved = self.filtered(lambda a: a.state in ('approved', 'doing', 'verify'))
            for action in approved:
                super(FinanceAction, action).write({'state': 'review', 'approved_by': False,
                                                   'plan_revision': action.plan_revision + 1})
        return result

    def action_transition(self, target):
        self.check_access_rights('write')
        self.check_access_rule('write')
        manager = self.env.su or self.env.user.has_group('biz_smart_finance.group_bsf_manager')
        edges = {'draft': {'review', 'cancelled'}, 'review': {'approved', 'draft', 'cancelled'},
                 'approved': {'doing', 'review', 'cancelled'}, 'doing': {'verify', 'review', 'cancelled'},
                 'verify': {'done', 'doing', 'review', 'cancelled'}, 'done': {'review'}, 'cancelled': {'draft'}}
        for rec in self:
            if target not in edges.get(rec.state, set()):
                raise UserError(_('ลำดับสถานะไม่ถูกต้อง'))
            if not manager and not (rec.owner_id == self.env.user and (rec.state, target) in {('approved', 'doing'), ('doing', 'verify')}):
                raise AccessError(_('ขั้นตอนนี้ต้องให้ Manager ดำเนินการ'))
            vals = {'state': target}
            if target == 'approved':
                if not rec.due_date:
                    raise UserError(_('ระบุวันครบกำหนดก่อนอนุมัติ'))
                if not (rec.owner_id.has_group('biz_smart_finance.group_bsf_action_owner') or rec.owner_id.has_group('biz_smart_finance.group_bsf_manager')):
                    raise UserError(_('ผู้รับงานต้องอยู่ในกลุ่มผู้รับ Action'))
                vals['approved_by'] = self.env.uid
            if target in ('verify', 'done') and not rec.result_evidence:
                raise UserError(_('ต้องมีหลักฐานผลการดำเนินงาน'))
            if target == 'done':
                if not rec.review_ids.filtered(lambda r: r.verified and r.action_revision == rec.plan_revision):
                    raise UserError(_('ฝ่ายการเงินต้องตรวจรับผลอย่างน้อยหนึ่งรายการ'))
                vals.update(verified_by=self.env.uid, progress=100)
            if target in ('review', 'draft'):
                vals.update(approved_by=False, verified_by=False)
                if rec.state not in ('draft', 'review', 'cancelled'):
                    vals['plan_revision'] = rec.plan_revision + 1
            super(FinanceAction, rec).write(vals)
            if target == 'approved':
                rec._schedule_followup(rec.owner_id)
        return True

    def action_submit(self): return self.action_transition('review')
    def action_approve(self): return self.action_transition('approved')
    def action_start(self): return self.action_transition('doing')
    def action_verify(self): return self.action_transition('verify')
    def action_done(self): return self.action_transition('done')
    def action_cancel(self): return self.action_transition('cancelled')
    def action_rework(self): return self.action_transition('doing')
    def action_reopen(self): return self.action_transition('review')

    def _schedule_followup(self, user):
        self.ensure_one()
        todo = self.env.ref('mail.mail_activity_data_todo')
        if not self.activity_ids.filtered(lambda a: a.user_id == user and a.activity_type_id == todo):
            self.with_context(mail_activity_quick_update=True).activity_schedule('mail.mail_activity_data_todo', user_id=user.id,
                                   date_deadline=self.due_date, summary='ติดตาม Action CFO')

    @api.model
    def _cron_overdue(self):
        actions = self.search([('state', 'in', ['approved', 'doing', 'verify']), ('due_date', '<', fields.Date.today())])
        managers = self.env.ref('biz_smart_finance.group_bsf_manager').users
        for action in actions:
            for user in managers.filtered(lambda u: u.active and action.company_id in u.company_ids):
                action._schedule_followup(user)


class ActionReview(models.Model):
    _name = 'biz.smart.finance.action.review'
    _description = 'ตรวจรับผล Action'
    _check_company_auto = True
    action_id = fields.Many2one('biz.smart.finance.action', required=True, ondelete='restrict')
    company_id = fields.Many2one(related='action_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    month = fields.Date(required=True, string='เดือนผลลัพธ์')
    action_revision = fields.Integer(readonly=True, copy=False, string='ฉบับแผนที่ตรวจรับ')
    base_period_id = fields.Many2one('biz.smart.finance.cost.period', check_company=True, string='เดือนฐาน')
    actual_period_id = fields.Many2one('biz.smart.finance.cost.period', check_company=True, string='เดือนผลจริง')
    evidence = fields.Text(required=True, string='หลักฐานและเหตุผลจัดสรรผลให้ Action นี้')
    raw_reduction = fields.Monetary(compute='_compute_saving', string='ค่าใช้จ่ายลดลงรวม')
    normalized_saving = fields.Monetary(compute='_compute_saving', string='ประหยัดปรับตามยอดขาย')
    calculation_note = fields.Char(compute='_compute_saving')
    accepted_saving = fields.Monetary(string='ผลประหยัดที่ตรวจรับสำหรับ Action นี้')
    verified = fields.Boolean(readonly=True, copy=False)
    verified_by = fields.Many2one('res.users', readonly=True, copy=False)
    verified_at = fields.Datetime(readonly=True, copy=False)
    _sql_constraints = [('review_once', 'unique(action_id, month, action_revision)', 'มีผลตรวจรับของงานนี้ในเดือนแล้ว')]

    @api.depends('base_period_id', 'actual_period_id', 'base_period_id.line_ids.amount', 'actual_period_id.line_ids.amount')
    def _compute_saving(self):
        for rec in self:
            rec.raw_reduction = rec.normalized_saving = 0
            rec.calculation_note = 'เลือกชุดข้อมูลฐานและผลจริงที่ยืนยันแล้ว หรือใช้หลักฐาน KPI ที่ไม่ใช่ต้นทุน'
            if rec.base_period_id and rec.actual_period_id:
                b, a = rec.base_period_id._metrics(), rec.actual_period_id._metrics()
                value = normalized_savings(b['sales'], b['variable'], b['fixed'], a['sales'], a['variable'], a['fixed'])
                rec.raw_reduction = b['cost'] - a['cost']
                rec.normalized_saving = (value - a['one_off']) if value is not None else 0
                rec.calculation_note = 'ปรับต้นทุนผันแปรตามยอดขายจริงและหักค่าใช้จ่ายครั้งเดียวของเดือนผลจริง' if value is not None else 'ยอดขายฐานเป็นศูนย์ คำนวณผลปรับกิจกรรมไม่ได้'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if any(k in vals or ('default_' + k) in self.env.context for k in ('verified', 'verified_by', 'verified_at', 'action_revision')):
                raise AccessError(_('ใช้ปุ่มตรวจรับ'))
            action_id = vals.get('action_id') or self.env.context.get('default_action_id')
            action = self.env['biz.smart.finance.action'].browse(action_id)
            action.check_access_rule('read')
            vals['action_revision'] = action.plan_revision
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) & {'verified', 'verified_by', 'verified_at', 'action_revision', 'action_id'} or any(self.mapped('verified')):
            raise AccessError(_('ผลตรวจรับแล้วแก้ไขไม่ได้'))
        return super().write(vals)

    def unlink(self):
        if any(self.mapped('verified')):
            raise AccessError(_('ลบผลตรวจรับแล้วไม่ได้'))
        return super().unlink()

    def action_accept(self):
        require_manager(self.env)
        self.check_access_rule('write')
        for rec in self:
            if rec.verified:
                continue
            if rec.action_revision != rec.action_id.plan_revision:
                raise UserError(_('แผนเปลี่ยนแล้ว ให้สร้างรายการตรวจรับสำหรับฉบับปัจจุบัน'))
            if rec.action_id.state != 'verify' or not rec.evidence or not finite_nonnegative(rec.accepted_saving):
                raise UserError(_('งานต้องรอตรวจผล มีหลักฐาน และผลตรวจรับไม่ติดลบ'))
            if rec.month.day != 1:
                raise UserError(_('ระบุวันที่ 1 ของเดือน'))
            if rec.accepted_saving:
                b, a = rec.base_period_id, rec.actual_period_id
                if not b or not a or b == a or a.month != rec.month or any(p.state not in ('confirmed', 'superseded') for p in (b, a)):
                    raise UserError(_('ผลประหยัดต้องมีชุดฐานและผลจริงที่ยืนยัน ตรงเดือน และเป็นคนละชุด'))
                if b.sales <= 0:
                    raise UserError(_('ยอดขายฐานต้องมากกว่าศูนย์'))
                self.env.cr.execute('SELECT id FROM res_company WHERE id=%s FOR UPDATE', [rec.company_id.id])
                # One baseline per actual month prevents double allocation under alternate bases.
                others = self.search([('company_id', '=', rec.company_id.id), ('month', '=', rec.month), ('verified', '=', True), ('accepted_saving', '>', 0), ('id', '!=', rec.id)])
                if any(o.base_period_id != b or o.actual_period_id != a for o in others) or sum(others.mapped('accepted_saving')) + rec.accepted_saving > max(0, rec.normalized_saving) + 0.01:
                    raise UserError(_('ผลตรวจรับรวมเกินผลประหยัดที่ปรับกิจกรรม หรือใช้ฐานคนละชุด'))
            super(ActionReview, rec).write({'verified': True, 'verified_by': self.env.uid, 'verified_at': fields.Datetime.now()})
        return True
