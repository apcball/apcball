from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError, UserError
from .bsf_cost_math import cost_metrics, finite_nonnegative

CATEGORIES = [
    ('sales', 'ยอดขายสุทธิ'), ('salary', 'เงินเดือน'), ('ot', 'OT'),
    ('benefits', 'สวัสดิการ'), ('employer', 'เงินสมทบนายจ้าง'),
    ('subcontract', 'ผู้รับเหมาช่วง'), ('material', 'วัตถุดิบ'),
    ('rent', 'ค่าเช่า'), ('utilities', 'สาธารณูปโภค'), ('transport', 'ขนส่ง'),
    ('marketing', 'การตลาด'), ('software', 'ระบบซอฟต์แวร์'),
    ('depreciation', 'ค่าเสื่อมราคา'), ('interest', 'ดอกเบี้ย'),
    ('tax', 'ภาษีเงินได้'), ('other', 'ค่าใช้จ่ายอื่น'),
]
PERSONNEL = {'salary', 'ot', 'benefits', 'employer'}


def require_manager(env):
    if not env.su and not env.user.has_group('biz_smart_finance.group_bsf_manager'):
        raise AccessError(_('ต้องเป็น CFO Cockpit / Manager'))


class CostDepartment(models.Model):
    _name = 'biz.smart.finance.cost.department'
    _description = 'ฝ่ายสำหรับการวิเคราะห์ต้นทุน'
    _check_company_auto = True
    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    revenue_center = fields.Boolean(string='ฝ่ายที่มียอดขาย')
    active = fields.Boolean(default=True)
    _sql_constraints = [('name_company', 'unique(name, company_id)', 'ชื่อฝ่ายซ้ำในบริษัท')]


class CostPeriod(models.Model):
    _name = 'biz.smart.finance.cost.period'
    _description = 'ข้อมูลต้นทุนรายเดือน'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'month desc, id desc'
    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    month = fields.Date(string='เดือน (วันที่ 1)', required=True,
                        default=lambda s: fields.Date.context_today(s).replace(day=1), tracking=True)
    state = fields.Selection([('draft', 'ร่าง'), ('confirmed', 'ยืนยัน'), ('superseded', 'ฉบับเดิม')],
                             default='draft', required=True, tracking=True, copy=False)
    origin_id = fields.Many2one('biz.smart.finance.cost.period', string='แก้ไขจากฉบับ', check_company=True, copy=False)
    confirmed_by = fields.Many2one('res.users', readonly=True, copy=False)
    confirmed_at = fields.Datetime(readonly=True, copy=False)
    complete = fields.Boolean(string='ยืนยันว่ารายได้และต้นทุนครบถ้วน', tracking=True)
    notes = fields.Text(string='ที่มา / หมายเหตุการแก้ไข')
    line_ids = fields.One2many('biz.smart.finance.cost.line', 'period_id', copy=True, string='รายได้และต้นทุน')
    staffing_ids = fields.One2many('biz.smart.finance.cost.staffing', 'period_id', copy=True, string='กำลังคน')
    target_profit = fields.Monetary(string='กำไรดำเนินงานเป้าหมาย')
    budget_cost = fields.Monetary(string='งบต้นทุนดำเนินงาน')
    has_budget = fields.Boolean(string='มีงบต้นทุน')
    sales = fields.Monetary(compute='_compute_totals', string='ยอดขาย')
    variable = fields.Monetary(compute='_compute_totals', string='ต้นทุนผันแปร')
    fixed = fields.Monetary(compute='_compute_totals', string='ต้นทุนคงที่')
    one_off = fields.Monetary(compute='_compute_totals', string='ค่าใช้จ่ายครั้งเดียว')
    personnel = fields.Monetary(compute='_compute_totals', string='ต้นทุนบุคลากร')
    operating_profit = fields.Monetary(compute='_compute_totals', string='กำไรดำเนินงาน')
    break_even = fields.Monetary(compute='_compute_totals', string='ยอดขายคุ้มทุน')
    calculation_note = fields.Char(compute='_compute_totals', string='สถานะการคำนวณ')

    @api.depends('month', 'company_id')
    def _compute_name(self):
        for rec in self:
            rec.name = '%s · %s' % (rec.company_id.name, rec.month or '')

    @api.constrains('month', 'target_profit', 'budget_cost', 'origin_id')
    def _check_period(self):
        for rec in self:
            if rec.month.day != 1 or not finite_nonnegative(rec.target_profit, rec.budget_cost):
                raise ValidationError(_('ระบุวันที่ 1 ของเดือน และจำนวนเงินไม่ติดลบ'))
            if rec.origin_id and (rec.origin_id.month != rec.month or rec.origin_id.company_id != rec.company_id):
                raise ValidationError(_('ฉบับแก้ไขต้องเป็นบริษัทและเดือนเดียวกัน'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state', self.env.context.get('default_state', 'draft')) != 'draft' or any(k in vals or ('default_' + k) in self.env.context for k in ('confirmed_by', 'confirmed_at')):
                raise AccessError(_('ยืนยันผ่านปุ่มยืนยันข้อมูลเท่านั้น'))
        return super().create(vals_list)

    def _lock_periods(self):
        if self.ids:
            self.env.cr.execute('SELECT id FROM biz_smart_finance_cost_period WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(self.ids)])
            self.invalidate_recordset(['state'])

    def write(self, vals):
        self._lock_periods()
        if set(vals) & {'state', 'confirmed_by', 'confirmed_at', 'origin_id'}:
            raise AccessError(_('ใช้ขั้นตอนยืนยันหรือสร้างฉบับแก้ไข'))
        business = set(vals) - {'message_follower_ids', 'activity_ids', 'message_main_attachment_id'}
        if business and any(rec.state != 'draft' for rec in self):
            raise UserError(_('ข้อมูลยืนยันแล้ว กรุณาสร้างฉบับแก้ไข'))
        return super().write(vals)

    def unlink(self):
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_('ลบฉบับยืนยันไม่ได้'))
        return super().unlink()

    def action_confirm(self):
        require_manager(self.env)
        self.check_access_rights('write')
        self.check_access_rule('write')
        for rec in self:
            # Serialize confirmations within a company; no duplicate current revision.
            self.env.cr.execute('SELECT id FROM res_company WHERE id=%s FOR UPDATE', [rec.company_id.id])
            rec._lock_periods()
            if rec.state != 'draft' or not rec.complete or not rec.line_ids:
                raise UserError(_('ต้องเป็นร่าง มีรายการ และตรวจความครบถ้วนก่อนยืนยัน'))
            if not rec.line_ids.filtered(lambda l: l.category == 'sales'):
                raise UserError(_('ต้องระบุแถวยอดขาย แม้ยอดเป็นศูนย์'))
            current = self.search([('company_id', '=', rec.company_id.id), ('month', '=', rec.month), ('state', '=', 'confirmed')])
            if current and current != rec.origin_id:
                raise UserError(_('มีฉบับยืนยันแล้ว ให้สร้างฉบับแก้ไขจากฉบับปัจจุบัน'))
            if current:
                super(CostPeriod, current).write({'state': 'superseded'})
            super(CostPeriod, rec).write({'state': 'confirmed', 'confirmed_by': self.env.uid,
                                        'confirmed_at': fields.Datetime.now()})
        return True

    def action_revision(self):
        self.ensure_one()
        require_manager(self.env)
        if self.state != 'confirmed':
            raise UserError(_('สร้างฉบับแก้ไขได้จากฉบับยืนยันปัจจุบัน'))
        revised = self.copy({'origin_id': self.id, 'complete': False})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': revised.id,
                'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}

    def action_import(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'biz.smart.finance.cost.import',
                'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new',
                'context': {'default_period_id': self.id, 'default_company_id': self.company_id.id}}

    def _metrics(self, department=None):
        self.ensure_one()
        lines = self.line_ids if department is None else self.line_ids.filtered(lambda l: l.department_id.id == department)
        staffing = self.staffing_ids if department is None else self.staffing_ids.filtered(lambda l: l.department_id.id == department)
        sales = sum(lines.filtered(lambda l: l.category == 'sales').mapped('amount'))
        operating = lines.filtered(lambda l: l.category not in ('sales', 'interest', 'tax'))
        recurring = operating.filtered(lambda l: not l.one_off)
        fixed = sum(l.amount * l.fixed_pct / 100 for l in recurring)
        variable = sum(l.amount * (1 - l.fixed_pct / 100) for l in recurring)
        one_off = sum(operating.filtered('one_off').mapped('amount'))
        complete = self.complete
        if department is not None:
            dept = self.env['biz.smart.finance.cost.department'].browse(department)
            complete = complete and bool(dept and dept.revenue_center) and all(lines.mapped('allocation_complete'))
        result = cost_metrics(sales, variable, fixed, one_off, self.target_profit if department is None else 0, complete)
        personnel = sum(lines.filtered(lambda l: l.category in PERSONNEL).mapped('amount'))
        cost_departments = set(lines.filtered(lambda l: l.category != 'sales').mapped(lambda l: l.department_id.id))
        staff_departments = set(staffing.mapped(lambda l: l.department_id.id))
        staffing_complete = bool(staffing) and all(staffing.mapped('complete')) and cost_departments.issubset(staff_departments)
        fte = sum(staffing.mapped('fte')) if staffing_complete else None
        result.update({
            'personnel': personnel, 'personnel_pct': personnel / sales * 100 if sales > 0 else None,
            'ot': sum(lines.filtered(lambda l: l.category == 'ot').mapped('amount')),
            'fte': fte, 'headcount': sum(staffing.mapped('headcount')) if fte is not None else None,
            'sales_per_fte': sales / fte if fte else None,
            'contribution_per_fte': (sales - variable) / fte if fte else None,
            'budget': self.budget_cost if self.has_budget and department is None else None,
            'cost': fixed + variable + one_off,
            'interest_tax': sum(lines.filtered(lambda l: l.category in ('interest', 'tax')).mapped('amount')),
        })
        return result

    @api.depends('line_ids.amount', 'line_ids.category', 'line_ids.fixed_pct', 'line_ids.one_off', 'complete', 'target_profit')
    def _compute_totals(self):
        for rec in self:
            values = rec._metrics()
            for key in ('sales', 'variable', 'fixed', 'one_off', 'personnel', 'operating_profit', 'break_even'):
                rec[key] = values[key] or 0
            rec.calculation_note = values['reason'] or _('คำนวณจากข้อมูลที่ยืนยันครบถ้วน')


class CostChildMixin(models.AbstractModel):
    _name = 'biz.smart.finance.cost.child.mixin'
    _description = 'Protect confirmed monthly cost details'
    _check_company_auto = True
    period_id = fields.Many2one('biz.smart.finance.cost.period', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='period_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    department_id = fields.Many2one('biz.smart.finance.cost.department', check_company=True,
                                    string='ฝ่าย (ว่าง = ยังไม่จัดสรร/ส่วนกลาง)')

    def _check_draft(self, new_period=None):
        periods = self.mapped('period_id')
        if new_period:
            periods |= self.env['biz.smart.finance.cost.period'].browse(new_period)
        periods.check_access_rule('write')
        periods._lock_periods()
        if any(p.state != 'draft' for p in periods):
            raise UserError(_('แก้ไขรายการได้เฉพาะข้อมูลร่าง'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_draft(vals.get('period_id') or self.env.context.get('default_period_id'))
        return super().create(vals_list)

    def write(self, vals):
        self._check_draft(vals.get('period_id') or self.env.context.get('default_period_id'))
        return super().write(vals)

    def unlink(self):
        self._check_draft()
        return super().unlink()


class CostLine(models.Model):
    _name = 'biz.smart.finance.cost.line'
    _inherit = 'biz.smart.finance.cost.child.mixin'
    _description = 'รายการต้นทุน/รายได้รายเดือน'
    name = fields.Char(string='รายการ', required=True)
    source_key = fields.Char(string='รหัสนำเข้า', index=True)
    category = fields.Selection(CATEGORIES, required=True, default='other', string='หมวด')
    amount = fields.Monetary(required=True, string='จำนวนเงิน')
    fixed_pct = fields.Float(default=100, string='ส่วนคงที่ (%)')
    one_off = fields.Boolean(string='ครั้งเดียว')
    allocation_complete = fields.Boolean(string='จัดสรรต้นทุนครบแล้ว')
    _sql_constraints = [('import_key', 'unique(period_id, source_key)', 'รหัสนำเข้าซ้ำในชุดข้อมูล')]

    @api.constrains('amount', 'fixed_pct', 'category', 'one_off')
    def _check_values(self):
        for rec in self:
            if not finite_nonnegative(rec.amount, rec.fixed_pct) or rec.fixed_pct > 100:
                raise ValidationError(_('จำนวนเงินต้องไม่ติดลบ และส่วนคงที่ต้องอยู่ระหว่าง 0–100%'))
            if rec.category == 'sales' and rec.one_off:
                raise ValidationError(_('รายการครั้งเดียวใช้กับค่าใช้จ่ายเท่านั้น'))


class CostStaffing(models.Model):
    _name = 'biz.smart.finance.cost.staffing'
    _inherit = 'biz.smart.finance.cost.child.mixin'
    _description = 'กำลังคนเฉลี่ยรายเดือน'
    headcount = fields.Float(string='จำนวนคนเฉลี่ย')
    fte = fields.Float(string='FTE เฉลี่ย')
    complete = fields.Boolean(string='ข้อมูลกำลังคนครบ')

    @api.constrains('headcount', 'fte', 'period_id', 'department_id')
    def _check_values(self):
        for rec in self:
            if not finite_nonnegative(rec.headcount, rec.fte):
                raise ValidationError(_('กำลังคนต้องไม่ติดลบ'))
            if self.search_count([('period_id', '=', rec.period_id.id), ('department_id', '=', rec.department_id.id), ('id', '!=', rec.id)]):
                raise ValidationError(_('กำลังคนของฝ่ายนี้มีแล้วในเดือนนี้'))


class CostConfig(models.Model):
    _inherit = 'biz.smart.finance.config'
    cost_personnel_pct = fields.Float(string='เพดานบุคลากร/ยอดขาย (%) — 0 ยังไม่ตั้ง')
    cost_ot_pct = fields.Float(string='เพดาน OT/บุคลากร (%) — 0 ยังไม่ตั้ง')
    cost_growth_gap_pp = fields.Float(string='เพดานค่าใช้จ่ายโตเกินยอดขาย (pp) — 0 ยังไม่ตั้ง')
    cost_cm_drop_pp = fields.Float(string='เพดานอัตรากำไรส่วนเกินลด (pp) — 0 ยังไม่ตั้ง')
    cost_dio_days = fields.Float(string='เพดาน DIO (วัน) — 0 ยังไม่ตั้ง')
    cost_channel_margin_pct = fields.Float(string='กำไรช่องทางขั้นต่ำ (%) — 0 ยังไม่ตั้ง')

    @api.constrains('cost_personnel_pct', 'cost_ot_pct', 'cost_growth_gap_pp', 'cost_cm_drop_pp', 'cost_dio_days', 'cost_channel_margin_pct')
    def _check_cost_thresholds(self):
        for rec in self:
            if not finite_nonnegative(*(rec[k] for k in ('cost_personnel_pct', 'cost_ot_pct', 'cost_growth_gap_pp', 'cost_cm_drop_pp', 'cost_dio_days', 'cost_channel_margin_pct'))):
                raise ValidationError(_('เกณฑ์ต้นทุนต้องเป็นค่าที่ไม่ติดลบ'))
