import json
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError
from .bsf_cost import CATEGORIES, require_manager
from .bsf_cost_math import cost_metrics
from .bsf_strategy import PLAYBOOKS


class StrategyService(models.AbstractModel):
    _name = 'biz.smart.finance.strategy.service'
    _description = 'CFO strategy analysis and rule evaluation'

    def _scope(self, filters):
        engine = self.env['biz.smart.finance.dashboard']
        engine._check_access()
        selected = (filters or {}).get('company_id')
        if selected and selected not in self.env.companies.ids:
            raise AccessError(_('บริษัทที่เลือกไม่อยู่ในสิทธิ์ที่เปิดใช้งาน'))
        f = engine._normalize_filters(filters or {})
        f['cids'] = [cid for cid in f['cids'] if cid in self.env.companies.ids]
        return f

    def _period_payload(self, period):
        m = period._metrics()
        categories = defaultdict(float)
        for line in period.line_ids:
            categories[line.category] += line.amount
        departments = []
        for key in sorted(set(period.line_ids.mapped('department_id').ids) | {0}):
            dept = self.env['biz.smart.finance.cost.department'].browse(key)
            departments.append({'id': key, 'name': dept.name if dept else 'ยังไม่จัดสรร / ส่วนกลาง', **period._metrics(key)})
        return {'id': period.id, 'month': str(period.month), **m,
                'categories': [{'key': k, 'name': dict(CATEGORIES)[k], 'amount': v} for k, v in categories.items()],
                'departments': departments}

    @api.model
    def get_cost_data(self, filters=None):
        f = self._scope(filters)
        month = f['as_of'].replace(day=1)
        result = []
        for company in self.env['res.company'].browse(f['cids']):
            company_f = self._scope(dict(filters or {}, company_id=company.id))
            month = company_f['as_of'].replace(day=1)
            fiscal_start = company_f['fy_start']
            periods = self.env['biz.smart.finance.cost.period'].search([
                ('company_id', '=', company.id), ('state', '=', 'confirmed'),
                ('month', '<=', month), ('month', '>=', min(fiscal_start.replace(day=1), month - relativedelta(months=1)))], order='month')
            current = periods.filtered(lambda p: p.month == month)
            previous = periods.filtered(lambda p: p.month == month - relativedelta(months=1))
            ytd = periods.filtered(lambda p: p.month >= fiscal_start.replace(day=1))
            totals = {k: sum(p._metrics()[k] for p in ytd) for k in ('sales', 'variable', 'fixed', 'one_off')}
            count = (month.year - fiscal_start.year) * 12 + month.month - fiscal_start.month + 1
            ytd_metrics = cost_metrics(**totals, target=sum(ytd.mapped('target_profit')), complete=len(ytd) == count and all(ytd.mapped('complete')))
            ytd_metrics.update({k: sum(p._metrics()[k] for p in ytd) for k in ('personnel', 'ot', 'cost')})
            ytd_metrics['personnel_pct'] = ytd_metrics['personnel'] / totals['sales'] * 100 if totals['sales'] > 0 else None
            ytd_metrics['budget'] = sum(ytd.mapped('budget_cost')) if ytd and all(ytd.mapped('has_budget')) else None
            company_row = {'month': str(month), 'fiscal_start': str(fiscal_start), 'company_id': company.id, 'company': company.name, 'currency': company.currency_id.name,
                           'current': self._period_payload(current) if current else None,
                           'previous': self._period_payload(previous) if previous else None,
                           'ytd': ytd_metrics, 'months_available': len(ytd), 'months_expected': count,
                           'history': [self._period_payload(p) for p in ytd],
                           'reconciliation': self._reconcile(current) if current else {'reason': 'ยังไม่มีข้อมูลเดือนที่เลือก'}}
            result.append(company_row)
        return {'companies': result, 'as_of': str(f['as_of']), 'month': str(month),
                'note': 'ยอดสรุปเต็มเดือนตามสกุลบริษัท แยกแต่ละบริษัท ไม่รวมต่างสกุลเข้าด้วยกัน',
                'is_manager': self.env.user.has_group('biz_smart_finance.group_bsf_manager')}

    def _reconcile(self, period):
        """Like-for-like operating sales and TOTAL expenses; never infer cost behavior from GL."""
        company = period.company_id
        end = period.month + relativedelta(months=1, days=-1)
        cfg = self.env['biz.smart.finance.config'].search([('company_id', '=', company.id)], limit=1)
        balances = []
        if cfg.gl_source == 'external':
            gl = self.env['biz.smart.finance.ext.gl'].search([('company_id', '=', company.id), ('state', '=', 'posted'),
                ('date_from', '=', period.month), ('date_to', '=', end)])
            if not gl:
                return {'reason': 'ไม่มี TB ยืนยันที่ตรงเดือน จึงยังเทียบไม่ได้'}
            for line in gl.line_ids:
                balances.append((line.account_type, line.debit - line.credit))
        else:
            # Access checked before this company-scoped accounting read, as in existing dashboard.
            rows = self.env['account.move.line'].sudo()._read_group([
                ('company_id', '=', company.id), ('parent_state', '=', 'posted'),
                ('date', '>=', period.month), ('date', '<=', end),
                ('account_id.account_type', 'in', ['income', 'expense', 'expense_direct_cost', 'expense_depreciation'])],
                groupby=['account_id'], aggregates=['balance:sum'])
            if not rows:
                return {'reason': 'ยังไม่มีรายการบัญชีลงแล้วในเดือนนี้'}
            balances = [(account.account_type, balance) for account, balance in rows]
        sales = -sum(v for t, v in balances if t == 'income')
        cost = sum(v for t, v in balances if t in ('expense', 'expense_direct_cost', 'expense_depreciation'))
        m = period._metrics()
        return {'reason': '', 'sales': sales, 'cost': cost, 'sales_difference': m['sales'] - sales,
                'cost_difference': m['cost'] + m['interest_tax'] - cost,
                'note': 'เทียบยอดขายดำเนินงานและค่าใช้จ่ายรวมรวมดอกเบี้ย/ภาษี ตรวจส่วนต่างของการจัดประเภทกับบัญชี'}

    @api.model
    def get_strategy_data(self, filters=None):
        f = self._scope(filters)
        domain = [('company_id', 'in', f['cids'])]
        goals = self.env['biz.smart.finance.goal'].search(domain + [('due_date', '>=', f['fy_start']), ('due_date', '<=', f['fy_end'])])
        issues = self.env['biz.smart.finance.issue'].search(domain + [('state', '!=', 'closed'), ('month', '<=', f['as_of'])], limit=100)
        actions = self.env['biz.smart.finance.action'].search(domain + [('state', 'not in', ['done', 'cancelled'])], limit=100)
        return {
            'goals': [{'id': g.id, 'name': g.name, 'company': g.company_id.name, 'quarter': g.quarter,
                       'baseline': g.baseline, 'target': g.target, 'actual': g.actual, 'monetary': g.unit == 'money',
                       'unit': g.company_id.currency_id.name if g.unit == 'money' else dict(g._fields['unit'].selection)[g.unit],
                       'progress': g.progress_pct, 'owner': g.owner_id.name, 'due': str(g.due_date)} for g in goals],
            'issues': [{'id': i.id, 'name': i.name, 'company': i.company_id.name, 'category': i.category,
                        'evidence': i.evidence, 'recommendation': i.recommendation,
                        'priority': i.priority, 'impact': i.financial_impact, 'currency': i.currency_id.name} for i in issues],
            'actions': [{'id': a.id, 'name': a.name, 'owner': a.owner_id.name, 'due': str(a.due_date or ''),
                         'state': dict(a._fields['state'].selection)[a.state], 'overdue': a.overdue,
                         'progress': a.progress, 'blocked': a.blocked} for a in actions],
            'is_manager': self.env.user.has_group('biz_smart_finance.group_bsf_manager'),
        }

    def _cost_candidates(self, company, month):
        period = self.env['biz.smart.finance.cost.period'].search([('company_id', '=', company.id), ('month', '=', month), ('state', '=', 'confirmed')], limit=1)
        if not period:
            return []
        m, rows = period._metrics(), []
        cfg = self.env['biz.smart.finance.config'].search([('company_id', '=', company.id)], limit=1)
        def add(key, name, category, evidence, amount=0):
            rows.append({'source_key': 'cost:' + key, 'name': name, 'category': category,
                         'evidence': evidence + '\nชุดต้นทุน #%s เดือน %s' % (period.id, month), 'financial_impact': max(0, amount)})
        if m['sales_gap'] and m['sales_gap'] > 0:
            add('breakeven', 'ยอดขายต่ำกว่าจุดคุ้มทุน', 'cost', 'ยอดขาย %.2f / จุดคุ้มทุน %.2f / ช่องว่าง %.2f' % (m['sales'], m['break_even'], m['sales_gap']), m['sales_gap'])
        if m['reason']:
            add('invalid_cm', 'ทบทวนโครงสร้างกำไรส่วนเกิน', 'cost', m['reason'])
        if cfg.cost_personnel_pct and m['personnel_pct'] is not None and m['personnel_pct'] > cfg.cost_personnel_pct:
            add('personnel', 'ต้นทุนบุคลากรต่อยอดขายเกินเกณฑ์', 'personnel', 'จริง %.2f%% / เกณฑ์ %.2f%%; ตรวจภาระงานและยอดขายก่อนสรุปสาเหตุ' % (m['personnel_pct'], cfg.cost_personnel_pct), m['personnel'])
        ot_pct = m['ot'] / m['personnel'] * 100 if m['personnel'] else None
        if cfg.cost_ot_pct and ot_pct is not None and ot_pct > cfg.cost_ot_pct:
            add('ot', 'OT ต่อค่าใช้จ่ายบุคลากรเกินเกณฑ์', 'personnel', 'จริง %.2f%% / เกณฑ์ %.2f%%' % (ot_pct, cfg.cost_ot_pct), m['ot'])
        if m['budget'] is not None and m['cost'] > m['budget']:
            add('budget', 'ต้นทุนดำเนินงานเกินงบ', 'budget', 'ต้นทุน %.2f / งบ %.2f' % (m['cost'], m['budget']), m['cost'] - m['budget'])
        previous = self.env['biz.smart.finance.cost.period'].search([('company_id', '=', company.id), ('month', '=', month - relativedelta(months=1)), ('state', '=', 'confirmed')], limit=1)
        if previous:
            p = previous._metrics()
            if cfg.cost_cm_drop_pp and m['contribution_pct'] is not None and p['contribution_pct'] is not None and p['contribution_pct'] - m['contribution_pct'] > cfg.cost_cm_drop_pp:
                add('cm_drop', 'อัตรากำไรส่วนเกินลดเกินเกณฑ์', 'cost', 'ลด %.2f pp / เกณฑ์ %.2f pp' % (p['contribution_pct'] - m['contribution_pct'], cfg.cost_cm_drop_pp))
            if cfg.cost_growth_gap_pp and p['cost'] > 0 and p['sales'] > 0:
                gap = (m['cost'] / p['cost'] - m['sales'] / p['sales']) * 100
                if gap > cfg.cost_growth_gap_pp:
                    add('growth', 'ค่าใช้จ่ายโตเร็วกว่ายอดขาย', 'cost', 'ส่วนต่างการเติบโต %.2f pp / เกณฑ์ %.2f pp' % (gap, cfg.cost_growth_gap_pp))
        return rows

    def _operating_candidates(self, company, filters):
        engine = self.env['biz.smart.finance.dashboard']
        filters = dict(filters or {}, company_id=company.id, scenario='base')
        payload = engine.get_dashboard_data(filters)
        normalized = engine._normalize_filters(filters)
        source_currency = normalized['presentation_currency']
        rows = []
        def add(key, name, category, evidence, impact=0, company_amount=False, **extra):
            amount = max(0, impact or 0)
            if not company_amount:
                amount = source_currency._convert(amount, company.currency_id, company, normalized['as_of'])
                evidence += '\nตัวเลขหลักฐานในสกุล %s; มูลค่าประเด็นแสดง %s' % (source_currency.name, company.currency_id.name)
            rows.append({'source_key': key, 'name': name, 'category': category,
                         'evidence': evidence, 'financial_impact': amount, **extra})
        cfg = self.env['biz.smart.finance.config'].search([('company_id', '=', company.id)], limit=1)
        shared = engine.sudo()._build_shared(normalized)
        shared['cash_forecast'] = engine.sudo()._build_cash_forecast(normalized, shared)
        engine.sudo()._build_margin(normalized, shared)
        for item in engine.sudo()._auto_alerts(normalized, shared):
            category = item['category'] if item['category'] in PLAYBOOKS else 'risk'
            add('radar:' + category, item['name'], category, item['indicator'], item.get('impact'))
        # Open risks beyond the dashboard's top-12 display cap remain eligible.
        for risk in self.env['biz.smart.finance.risk'].search([('company_id', '=', company.id), ('state', '!=', 'closed')]):
            add('risk:%s' % risk.id, risk.name, 'risk', risk.early_warning or risk.name, risk.financial_impact, company_amount=True, risk_id=risk.id)
        if payload['ap']['conflict']['has_conflict']:
            add('ap:conflict', 'แผนจ่ายอยู่ในช่วงเงินสดขาด', 'ap', json.dumps(payload['ap']['conflict']['weeks'], ensure_ascii=False), payload['ap']['overdue_total'])
        controlling = payload['controlling']
        if controlling.get('configured') and controlling.get('totals', {}).get('over_count'):
            totals = controlling['totals']
            add('budget:commitment', 'ต้นทุนรวมภาระผูกพันเกินงบ', 'budget', json.dumps(totals, ensure_ascii=False), max(0, -totals.get('available', 0)))
        ratios = payload['ratios']['summary']
        if cfg.dso_target_days and ratios.get('dso_days') is not None and ratios['dso_days'] > cfg.dso_target_days:
            add('ar:dso', 'DSO สูงกว่าเป้า', 'ar', 'DSO %s วัน / เป้า %s วัน' % (ratios['dso_days'], cfg.dso_target_days))
        if cfg.cost_dio_days and ratios.get('dio_days') is not None and ratios['dio_days'] > cfg.cost_dio_days:
            add('inventory:dio', 'DIO สูงกว่าเป้า', 'inventory', 'DIO %s วัน / เป้า %s วัน; ข้อมูลรวมไม่บ่งชี้สินค้ารายตัว' % (ratios['dio_days'], cfg.cost_dio_days))
        capital = engine.sudo()._capital_structure(shared)
        if capital['debt_configured'] and capital['equity'] > 0 and capital['nde_target'] is not None:
            actual = capital['net_debt'] / capital['equity']
            if actual > capital['nde_target']:
                add('capital:nde', 'Net Debt / Equity เกินเป้า', 'capital', 'จริง %.2f เท่า / เป้า %.2f เท่า' % (actual, capital['nde_target']), capital['net_debt'])
        if cfg.cost_channel_margin_pct:
            channel = engine.get_channel_data(filters)['channel']
            for row in channel['matrix']['rows']:
                totals = row.get('totals', {})
                pct = totals.get('gross_pct')
                if row.get('key', -1) >= 0 and pct is not None and pct < cfg.cost_channel_margin_pct:
                    add('channel:%s' % row['key'], 'กำไรช่องทางต่ำกว่าเป้า: %s' % row['name'], 'channel', 'กำไรขั้นต้น %.2f%% / เป้า %.2f%% (ไม่ใช่ Contribution Margin)' % (pct, cfg.cost_channel_margin_pct))
        return rows

    @api.model
    def action_evaluate(self, filters=None):
        require_manager(self.env)
        f = self._scope(filters)
        month = f['as_of'].replace(day=1)
        Issue = self.env['biz.smart.finance.issue']
        count = 0
        for company in self.env['res.company'].browse(f['cids']):
            candidates = self._cost_candidates(company, month) + self._operating_candidates(company, filters)
            self.env.cr.execute('SELECT id FROM res_company WHERE id=%s FOR UPDATE', [company.id])
            for candidate in {c['source_key']: c for c in candidates}.values():
                candidate.update(company_id=company.id, month=month, observed_at=fields.Datetime.now(),
                                 recommendation=PLAYBOOKS[candidate['category']],
                                 suspected_cause='ตรวจรายละเอียดต้นทางและยืนยันกับเจ้าของกระบวนการก่อนสรุปสาเหตุ')
                existing = Issue.search([('company_id', '=', company.id), ('month', '=', month), ('source_key', '=', candidate['source_key'])], limit=1)
                if existing:
                    # Preserve confirmed cause and the owner's action plan on repeated evaluation.
                    candidate.pop('suspected_cause')
                    candidate.pop('recommendation')
                    existing.write(candidate)
                else:
                    Issue.create(candidate)
                count += 1
        return {'evaluated': count}
