import hashlib
import json
from html import escape
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from .bsf_cost import require_manager
from .bsf_cost_math import cost_metrics, finite_nonnegative


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class CostScenario(models.Model):
    _name = 'biz.smart.finance.cost.scenario'
    _description = 'จำลองทางเลือก CFO'
    _inherit = ['mail.thread']
    _check_company_auto = True
    name = fields.Char(required=True, string='ทางเลือก')
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    base_period_id = fields.Many2one('biz.smart.finance.cost.period', required=True, check_company=True,
                                     domain="[('company_id', '=', company_id), ('state', '=', 'confirmed')]", string='ฐานต้นทุน')
    kind = fields.Selection([('sales', 'เพิ่มยอดขาย'), ('cost', 'ลดต้นทุน'), ('mixed', 'ทำทั้งสองอย่าง')], required=True, default='mixed')
    start_month = fields.Date(required=True, default=lambda s: fields.Date.context_today(s).replace(day=1), string='เดือนเริ่มผล')
    months = fields.Integer(default=12, required=True, string='จำนวนเดือน (1–18)')
    new_sales = fields.Monetary(string='ยอดขายใหม่ต่อเดือน')
    variable_pct = fields.Float(string='ต้นทุนผันแปรใหม่/ยอดขาย (%)')
    one_time_cost = fields.Monetary(string='ค่าใช้จ่ายเปลี่ยนแผนครั้งเดียว')
    assumptions = fields.Text(required=True, string='สมมติฐานกำลังผลิต คุณภาพ ส่งมอบ และบริการ')
    effect_ids = fields.One2many('biz.smart.finance.cost.effect', 'scenario_id', copy=True, string='ลดต้นทุนคงที่')
    cash_ids = fields.One2many('biz.smart.finance.cost.cash.effect', 'scenario_id', copy=True, string='ผลเงินสด (ส่วนต่างจากฐาน)')
    cash_complete = fields.Boolean(string='ยืนยันจังหวะเงินสดครบ รวมค่าใช้จ่ายดำเนินแผน')
    baseline_json = fields.Json(readonly=True, copy=False)
    forecast_json = fields.Json(readonly=True, copy=False)
    forecast_hash = fields.Char(readonly=True, copy=False)
    captured_at = fields.Datetime(readonly=True, copy=False)
    result_json = fields.Json(readonly=True, copy=False)
    result_html = fields.Html(readonly=True, copy=False, string='ผลเปรียบเทียบ')
    stale = fields.Boolean(readonly=True, copy=False, string='ฐานเปลี่ยนแล้ว')
    _protected = {'baseline_json', 'forecast_json', 'forecast_hash', 'captured_at', 'result_json', 'result_html', 'stale'}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if set(vals) & self._protected or any(('default_' + k) in self.env.context for k in self._protected):
                raise AccessError(_('ใช้ปุ่มเก็บฐานและจำลอง'))
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) & self._protected:
            raise AccessError(_('แก้ข้อมูลผลคำนวณโดยตรงไม่ได้'))
        if any(self.mapped('captured_at')) and set(vals) & {'base_period_id', 'company_id'}:
            raise UserError(_('ฐานถูกบันทึกแล้ว ให้ทำสำเนาสถานการณ์เพื่อเปลี่ยนฐาน'))
        result = super().write(vals)
        if set(vals) - {'message_follower_ids', 'message_main_attachment_id'}:
            super().write({'result_json': False, 'result_html': False})
        return result

    @api.constrains('start_month', 'months', 'new_sales', 'variable_pct', 'one_time_cost')
    def _check_inputs(self):
        for rec in self:
            if rec.start_month.day != 1 or not 1 <= rec.months <= 18 or not finite_nonnegative(rec.new_sales, rec.variable_pct, rec.one_time_cost):
                raise ValidationError(_('ตรวจเดือน ระยะเวลา 1–18 และจำนวนเงิน/อัตราที่ไม่ติดลบ'))

    def _forecast(self):
        self.ensure_one()
        payload = self.env['biz.smart.finance.dashboard'].get_forecast_data({'company_id': self.company_id.id, 'scenario': 'base'})
        forecast = payload['forecast']
        echo = payload.get('filters') or {}
        source = self.env['res.currency'].with_context(active_test=False).search([('name', '=', echo.get('currency') or self.currency_id.name)], limit=1)
        if not source:
            raise UserError(_('ไม่พบสกุลเงินของ Forecast ฐาน'))
        at_date = fields.Date.to_date(echo.get('as_of')) or fields.Date.context_today(self)
        rate = source._convert(1, self.currency_id, self.company_id, at_date, round=False)
        cash = forecast.get('cash') or {}
        return {'months': forecast.get('months', []), 'source_forecast': forecast,
                'source_currency': source.name, 'cash_currency': self.currency_id.name,
                'fx_date': str(at_date), 'fx_rate': rate,
                'cash': {'closing': [v * rate for v in cash.get('closing', [])],
                         'opening': cash.get('opening', 0) * rate,
                         'min_cash': cash.get('min_cash', 0) * rate}}

    def action_capture(self):
        require_manager(self.env)
        self.check_access_rule('write')
        for rec in self:
            if rec.captured_at:
                raise UserError(_('เก็บฐานแล้ว ให้ทำสำเนาเพื่อเก็บฐานฉบับใหม่'))
            if rec.base_period_id.state != 'confirmed' or not rec.base_period_id.complete:
                raise UserError(_('เลือกข้อมูลต้นทุนที่ยืนยันครบถ้วน'))
            base = rec.base_period_id._metrics()
            forecast = rec._forecast()
            super(CostScenario, rec).write({'baseline_json': base, 'forecast_json': forecast,
                'forecast_hash': fingerprint(forecast), 'captured_at': fields.Datetime.now(),
                'new_sales': base['sales'], 'variable_pct': base['variable'] / base['sales'] * 100 if base['sales'] else 0})
        return True

    def action_simulate(self):
        require_manager(self.env)
        self.check_access_rule('write')
        for rec in self:
            if not rec.captured_at:
                raise UserError(_('เก็บฐานก่อนจำลอง'))
            is_stale = rec.base_period_id.state != 'confirmed' or fingerprint(rec._forecast()) != rec.forecast_hash
            super(CostScenario, rec).write({'stale': is_stale})
            if is_stale:
                super(CostScenario, rec).write({'result_json': False,
                    'result_html': '<p>ฐานเปลี่ยนแล้ว กรุณาทำสำเนาและเก็บฐานใหม่ก่อนจำลอง</p>'})
                continue
            base = rec.baseline_json
            reductions, alternatives = {}, {}
            for effect in rec.effect_ids:
                line = effect.source_line_id
                if line.period_id != rec.base_period_id or line.category in ('sales', 'interest', 'tax') or line.one_off:
                    raise UserError(_('รายการลดต้นทุนต้องมาจากต้นทุนคงที่ประจำในชุดฐาน'))
                key = line.id
                reductions[key] = reductions.get(key, 0) + effect.monthly_saving
                if reductions[key] > line.amount * line.fixed_pct / 100 + 0.01:
                    raise UserError(_('ลดต้นทุนซ้ำหรือเกินต้นทุนคงที่ฐาน: %s') % line.name)
                if effect.alternative_group:
                    choice = effect.action_id.id or ('effect', effect.id)
                    old = alternatives.setdefault(effect.alternative_group, choice)
                    if old != choice:
                        raise UserError(_('เลือกเพียงหนึ่ง Action ในกลุ่มทางเลือก %s') % effect.alternative_group)
            fixed_saving = sum(reductions.values())
            base_variable_pct = base['variable'] / base['sales'] * 100 if base['sales'] else None
            if rec.kind == 'sales' and (fixed_saving or (base_variable_pct is not None and abs(rec.variable_pct - base_variable_pct) > .0001)):
                raise UserError(_('ทางเลือกเพิ่มยอดขายใช้โครงสร้างต้นทุนเดิม เลือกแบบผสมเพื่อปรับต้นทุนด้วย'))
            if rec.kind == 'cost' and abs(rec.new_sales - base['sales']) > .01:
                raise UserError(_('ทางเลือกลดต้นทุนใช้ยอดขายเดิม เลือกแบบผสมเพื่อเปลี่ยนยอดขายด้วย'))
            after = cost_metrics(rec.new_sales, rec.new_sales * rec.variable_pct / 100,
                                 base['fixed'] - fixed_saving, 0, rec.base_period_id.target_profit)
            rows = []
            cumulative = 0
            # Baseline is a constant monthly operating run-rate; historical one-offs do not repeat.
            for i in range(rec.months):
                delta = after['recurring_profit'] - base['recurring_profit'] - (rec.one_time_cost if i == 0 else 0)
                cumulative += delta
                rows.append({'month': str(rec.start_month + relativedelta(months=i)),
                             'base_profit': base['recurring_profit'],
                             'after_profit': after['recurring_profit'] - (rec.one_time_cost if i == 0 else 0),
                             'net_benefit': delta, 'cumulative': cumulative})
            cash = rec._cash_simulation() if rec.cash_complete else {'reason': 'ยังไม่ยืนยันจังหวะเงินสด ผลกำไรไม่เท่ากับเงินสด', 'rows': []}
            result = {'baseline': base, 'after': after, 'monthly_fixed_saving': fixed_saving,
                      'rows': rows, 'net_benefit': cumulative, 'cash': cash,
                      'basis_note': 'ฐานเป็นยอดดำเนินงานประจำคงที่รายเดือน ไม่ทำซ้ำค่าใช้จ่ายครั้งเดียวในอดีต'}
            html = '<p>%s</p><table class="table table-sm"><thead><tr><th>ตัวชี้วัด</th><th>ก่อน</th><th>หลัง (รายเดือนประจำ)</th></tr></thead><tbody>' % result['basis_note']
            for label, key in [('ยอดขาย', 'sales'), ('ต้นทุนผันแปร', 'variable'), ('ต้นทุนคงที่', 'fixed'), ('กำไรดำเนินงานประจำ', 'recurring_profit'), ('ยอดขายคุ้มทุนประจำ', 'recurring_break_even'), ('ยอดขายเพื่อกำไรเป้าหมาย', 'target_sales')]:
                values = [base.get(key), after.get(key)]
                if key == 'target_sales':
                    values[0] = cost_metrics(base['sales'], base['variable'], base['fixed'], target=rec.base_period_id.target_profit)['target_sales']
                html += '<tr><td>%s</td>%s</tr>' % (label, ''.join('<td>%s</td>' % ('%.2f' % v if v is not None else 'คำนวณไม่ได้') for v in values))
            html += '</tbody></table><p>ผลสุทธิสะสม: %.2f | ค่าใช้จ่ายเปลี่ยนแผน: %.2f</p>' % (cumulative, rec.one_time_cost)
            html += '<table class="table table-sm"><tr><th>เดือน</th><th>กำไรหลังแผน</th><th>ประโยชน์สุทธิสะสม</th></tr>'
            for row in rows:
                html += '<tr><td>%s</td><td>%.2f</td><td>%.2f</td></tr>' % (row['month'], row['after_profit'], row['cumulative'])
            html += '</table><p>%s</p>' % escape(cash.get('reason') or 'ผลเงินสดใช้จังหวะที่ผู้วางแผนยืนยัน')
            if cash.get('rows'):
                html += '<table class="table table-sm"><tr><th>เดือน</th><th>เงินสดฐาน</th><th>เงินสดหลังแผน</th></tr>'
                for row in cash['rows']:
                    html += '<tr><td>%s</td><td>%.2f</td><td>%.2f</td></tr>' % (escape(row['label']), row['base'], row['after'])
                html += '</table><p>เงินสดต่ำสุดหลังแผน %.2f | ยอดส่วนต่างนอกช่วง %.2f</p>' % (cash['minimum'], cash['overflow_delta'])
            super(CostScenario, rec).write({'result_json': result, 'result_html': html})
        return True

    def _cash_simulation(self):
        self.ensure_one()
        forecast = self.forecast_json
        months = forecast.get('months', [])
        closing = forecast.get('cash', {}).get('closing', [])
        if not months or not closing:
            raise UserError(_('ไม่มีฐานเงินสดสำหรับจำลอง'))
        labels = [m.get('label', '') for m in months]
        # Monthly grids include a final overflow bucket. Normal months have a start.
        starts = [fields.Date.to_date(m.get('start') or m.get('date_from')) for m in months if m.get('start') or m.get('date_from')]
        if not starts:
            # Forecast exposes year/month rather than date objects in some versions.
            starts = [fields.Date.to_date('%04d-%02d-01' % (m['year'], m['month'])) for m in months if m.get('year') and m.get('month')]
        if not starts:
            raise UserError(_('ฐาน Forecast ไม่มีวันที่รายเดือน'))
        deltas = [0.0] * len(closing)
        used = set()
        shifts = {}
        for entry in self.cash_ids:
            if entry.reference in used:
                raise UserError(_('รหัสผลเงินสดซ้ำ'))
            used.add(entry.reference)
            if entry.shift_key:
                shifts[entry.shift_key] = shifts.get(entry.shift_key, 0) + entry.delta
            if entry.month < starts[0]:
                raise UserError(_('เดือนเงินสดต้องไม่ก่อนช่วง Forecast ฐาน'))
            index = next((i for i, start in enumerate(starts) if start.year == entry.month.year and start.month == entry.month.month), len(closing) - 1)
            deltas[index] += entry.delta
        if any(abs(total) > 0.01 for total in shifts.values()):
            raise UserError(_('การเลื่อนเงินแต่ละกลุ่มต้องหักเดือนเดิมและเพิ่มเดือนใหม่รวมเป็นศูนย์'))
        cumulative, rows = 0, []
        floor = forecast.get('cash', {}).get('min_cash', 0)
        for i, value in enumerate(closing):
            cumulative += deltas[i]
            rows.append({'label': labels[i], 'base': value, 'after': value + cumulative,
                         'below_floor': value + cumulative < floor})
        return {'rows': rows, 'minimum': min(r['after'] for r in rows),
                'overflow_delta': deltas[-1], 'total_delta': sum(deltas), 'reason': ''}


class ScenarioEffect(models.Model):
    _name = 'biz.smart.finance.cost.effect'
    _description = 'ผลลดต้นทุนคงที่ของ Action'
    _check_company_auto = True
    scenario_id = fields.Many2one('biz.smart.finance.cost.scenario', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='scenario_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    action_id = fields.Many2one('biz.smart.finance.action', check_company=True)
    source_line_id = fields.Many2one('biz.smart.finance.cost.line', required=True, check_company=True, string='รายการฐาน')
    monthly_saving = fields.Monetary(required=True, string='ลดต่อเดือน')
    alternative_group = fields.Char(string='กลุ่มทางเลือกที่ใช้พร้อมกันไม่ได้')

    @api.constrains('monthly_saving', 'source_line_id', 'scenario_id')
    def _check_effect(self):
        for rec in self:
            if not finite_nonnegative(rec.monthly_saving) or rec.source_line_id.period_id != rec.scenario_id.base_period_id:
                raise ValidationError(_('ผลลดต้องไม่ติดลบและอ้างรายการจากชุดฐาน'))

    @api.model_create_multi
    def create(self, vals):
        records = super().create(vals)
        records.mapped('scenario_id')._invalidate_result()
        return records

    def write(self, vals):
        scenarios = self.mapped('scenario_id')
        result = super().write(vals)
        (scenarios | self.mapped('scenario_id'))._invalidate_result()
        return result

    def unlink(self):
        scenarios = self.mapped('scenario_id')
        result = super().unlink()
        scenarios._invalidate_result()
        return result


class CashEffect(models.Model):
    _name = 'biz.smart.finance.cost.cash.effect'
    _description = 'จังหวะเงินสดส่วนต่างจาก Forecast ฐาน'
    _inherit = 'biz.smart.finance.cost.effect'
    source_line_id = fields.Many2one(required=False)
    monthly_saving = fields.Monetary(required=False, default=0)
    reference = fields.Char(required=True, string='รหัสอ้างอิงไม่ซ้ำ')
    shift_key = fields.Char(string='กลุ่มเลื่อนเงิน (กลุ่มเดียวกันต้องรวมเป็นศูนย์)')
    month = fields.Date(required=True, string='เดือนเงินสด')
    delta = fields.Monetary(string='ส่วนต่างเงินสด (+ รับ/ประหยัด, − จ่าย/รับลด)')
    note = fields.Char(required=True, string='ที่มา / สำหรับเลื่อนเงินให้กรอกหักเดือนเดิมและเพิ่มเดือนใหม่')
    _sql_constraints = [('cash_ref', 'unique(scenario_id, reference)', 'รหัสเงินสดซ้ำ')]

    @api.constrains('monthly_saving', 'source_line_id', 'scenario_id', 'delta', 'month')
    def _check_effect(self):
        import math
        for rec in self:
            if not math.isfinite(rec.delta) or rec.month.day != 1:
                raise ValidationError(_('ระบุวันที่ 1 และผลเงินสดที่เป็นตัวเลข'))


class ScenarioInvalidation(models.Model):
    _inherit = 'biz.smart.finance.cost.scenario'

    def _invalidate_result(self):
        super(CostScenario, self).write({'result_json': False, 'result_html': False})
