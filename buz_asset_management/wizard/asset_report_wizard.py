# -*- coding: utf-8 -*-
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero

from ..services.ledger import AssetLedger, period_movements


class _ReportBase(models.AbstractModel):
    _name = 'buz.asset.report.base'
    _description = 'ฐานรายงานทรัพย์สิน'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, string='บริษัท')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    def _check_company_access(self):
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise AccessError(_("ไม่มีสิทธิ์เข้าถึงบริษัท %s", self.company_id.display_name))

    def _require_accountant(self):
        if not self.env.user.has_group('buz_asset_management.group_asset_accountant'):
            raise AccessError(_("เฉพาะนักบัญชีทรัพย์สินที่ดูรายงานนี้ได้"))


# ----------------------------------------------------------------------
# Asset <-> GL reconciliation
# ----------------------------------------------------------------------
class BuzAssetReconcileWizard(models.TransientModel):
    _name = 'buz.asset.reconcile.wizard'
    _inherit = 'buz.asset.report.base'
    _description = 'กระทบยอดทะเบียนทรัพย์สินกับ GL'

    date_to = fields.Date(required=True, default=fields.Date.context_today, string='ณ วันที่')
    line_ids = fields.One2many('buz.asset.reconcile.line', 'wizard_id', readonly=True, string='รายการ')
    gl_nbv = fields.Monetary(currency_field='currency_id', readonly=True, string='มูลค่าตามบัญชี (GL)')
    subledger_nbv = fields.Monetary(currency_field='currency_id', readonly=True, string='มูลค่าตามบัญชี (ทะเบียน)')
    nbv_variance = fields.Monetary(currency_field='currency_id', readonly=True, string='ผลต่างมูลค่าตามบัญชี')
    unmapped_asset_ids = fields.Many2many(
        'buz.asset', 'buz_asset_reconcile_unmapped_rel', 'wizard_id', 'asset_id', readonly=True,
        string='ทรัพย์สินที่หมวดหมู่ยังไม่ตั้งบัญชี')
    computed = fields.Boolean(readonly=True)

    def action_compute(self):
        self._require_accountant()
        self._check_company_access()
        ledger = AssetLedger(self.env, self.company_id, self.date_to)
        costs, accums, unposted = ledger.cost_by_asset(), ledger.accumulated_by_asset(), ledger.unposted_due_by_asset()
        rounding = self.currency_id.rounding
        rows = {}  # (kind, account) -> dict
        unmapped = self.env['buz.asset']
        for asset in ledger.live_assets():
            category = asset.category_id
            if not category.asset_account_id or not category.depreciation_account_id:
                unmapped |= asset
                continue
            cost_row = rows.setdefault(('cost', category.asset_account_id), defaultdict(float, assets=self.env['buz.asset']))
            cost_row['sub'] += costs[asset]
            cost_row['assets'] |= asset
            acc_row = rows.setdefault(('accumulated', category.depreciation_account_id),
                                      defaultdict(float, assets=self.env['buz.asset']))
            acc_row['sub'] += accums.get(asset, 0.0)
            acc_row['due'] += unposted.get(asset, 0.0)
            acc_row['assets'] |= asset
        # Accounts configured on categories show up even when no asset is on them (GL may still hold a balance).
        for category in self.env['buz.asset.category'].search([('company_id', '=', self.company_id.id)]):
            if category.asset_account_id:
                rows.setdefault(('cost', category.asset_account_id), defaultdict(float, assets=self.env['buz.asset']))
            if category.depreciation_account_id:
                rows.setdefault(('accumulated', category.depreciation_account_id),
                                defaultdict(float, assets=self.env['buz.asset']))
        gl = ledger.gl_balances(self.env['account.account'].browse([acc.id for _k, acc in rows]))
        commands, gl_cost, gl_accum, sub_cost, sub_accum = [], 0.0, 0.0, 0.0, 0.0
        for (kind, account), data in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][1].code)):
            # Accumulated depreciation is a credit balance: show it positive.
            gl_balance = gl.get(account.id, 0.0) * (1 if kind == 'cost' else -1)
            if kind == 'cost':
                gl_cost, sub_cost = gl_cost + gl_balance, sub_cost + data['sub']
            else:
                gl_accum, sub_accum = gl_accum + gl_balance, sub_accum + data['sub']
            commands.append(Command.create({
                'kind': kind, 'account_id': account.id, 'gl_balance': gl_balance,
                'subledger_balance': data['sub'], 'unposted_due': data['due'],
                'asset_ids': [Command.set(data['assets'].ids)],
                'asset_count': len(data['assets'])}))
        self.line_ids.unlink()
        self.write({
            'line_ids': commands, 'gl_nbv': gl_cost - gl_accum, 'subledger_nbv': sub_cost - sub_accum,
            'nbv_variance': (gl_cost - gl_accum) - (sub_cost - sub_accum),
            'unmapped_asset_ids': [Command.set(unmapped.ids)], 'computed': True})
        return self._reopen()

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'current', 'name': _('กระทบยอดทะเบียนทรัพย์สินกับ GL')}


class BuzAssetReconcileLine(models.TransientModel):
    _name = 'buz.asset.reconcile.line'
    _description = 'รายการกระทบยอดทะเบียนทรัพย์สินกับ GL'
    _order = 'kind, account_id'

    wizard_id = fields.Many2one('buz.asset.reconcile.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')
    kind = fields.Selection([('cost', 'ราคาทุน'), ('accumulated', 'ค่าเสื่อมราคาสะสม')], required=True,
                            string='ประเภท')
    account_id = fields.Many2one('account.account', required=True, string='บัญชี')
    gl_balance = fields.Monetary(currency_field='currency_id', string='ยอด GL')
    subledger_balance = fields.Monetary(currency_field='currency_id', string='ยอดทะเบียน (ลงบัญชีแล้ว)')
    variance = fields.Monetary(currency_field='currency_id', compute='_compute_variance', string='ผลต่าง (GL - ทะเบียน)')
    unposted_due = fields.Monetary(
        currency_field='currency_id', string='ค่าเสื่อมครบกำหนดยังไม่ลงบัญชี',
        help="ตามแผน ไม่ใช่ยอดบัญชี: อธิบายผลต่างของค่าเสื่อมสะสมได้บางส่วน")
    asset_count = fields.Integer(string='จำนวนทรัพย์สิน')
    asset_ids = fields.Many2many('buz.asset', 'buz_asset_reconcile_line_asset_rel', 'line_id', 'asset_id')
    matched = fields.Boolean(compute='_compute_variance', string='ตรงกัน')

    @api.depends('gl_balance', 'subledger_balance')
    def _compute_variance(self):
        for line in self:
            line.variance = line.gl_balance - line.subledger_balance
            line.matched = float_is_zero(line.variance, precision_rounding=line.currency_id.rounding or 0.01)

    def action_open_gl(self):
        self.ensure_one()
        date_to = self.wizard_id.date_to
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move.line', 'view_mode': 'tree,form',
                'name': _('รายการบัญชี %s', self.account_id.display_name),
                'domain': [('account_id', '=', self.account_id.id), ('company_id', '=', self.wizard_id.company_id.id),
                           ('parent_state', '=', 'posted'), ('date', '<=', date_to)]}

    def action_open_assets(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'buz.asset', 'view_mode': 'tree,form',
                'name': _('ทรัพย์สินในบัญชี %s', self.account_id.display_name),
                'domain': [('id', 'in', self.asset_ids.ids)]}


# ----------------------------------------------------------------------
# Roll-forward
# ----------------------------------------------------------------------
class BuzAssetRollforwardWizard(models.TransientModel):
    _name = 'buz.asset.rollforward.wizard'
    _inherit = 'buz.asset.report.base'
    _description = 'ความเคลื่อนไหวทรัพย์สิน (Roll-forward)'

    date_from = fields.Date(required=True, default=lambda s: fields.Date.context_today(s).replace(month=1, day=1),
                            string='ตั้งแต่วันที่')
    date_to = fields.Date(required=True, default=fields.Date.context_today, string='ถึงวันที่')
    line_ids = fields.One2many('buz.asset.rollforward.line', 'wizard_id', readonly=True, string='รายการ')
    computed = fields.Boolean(readonly=True)

    def action_compute(self):
        self._require_accountant()
        self._check_company_access()
        if self.date_from > self.date_to:
            raise UserError(_("วันที่เริ่มต้องไม่เกินวันที่สิ้นสุด"))
        opening = AssetLedger(self.env, self.company_id, self.date_from - relativedelta(days=1))
        closing = AssetLedger(self.env, self.company_id, self.date_to)
        o_cost, o_acc = opening.cost_by_asset(), opening.accumulated_by_asset()
        c_cost, c_acc = closing.cost_by_asset(), closing.accumulated_by_asset()
        additions, depreciation, disp_cost, disp_acc = period_movements(
            self.env, self.company_id, self.date_from, self.date_to)

        def by_category(mapping):
            out = defaultdict(float)
            for asset, amount in mapping.items():
                out[asset.category_id] += amount
            return out
        o_cost, o_acc, c_cost, c_acc = by_category(o_cost), by_category(o_acc), by_category(c_cost), by_category(c_acc)
        categories = set().union(o_cost, c_cost, o_acc, c_acc, additions, depreciation, disp_cost, disp_acc)
        commands = []
        for category in sorted(categories, key=lambda c: c.name):
            commands.append(Command.create({
                'category_id': category.id,
                'opening_cost': o_cost.get(category, 0.0), 'additions': additions.get(category, 0.0),
                'disposals_cost': disp_cost.get(category, 0.0), 'closing_cost': c_cost.get(category, 0.0),
                'opening_accum': o_acc.get(category, 0.0), 'depreciation': depreciation.get(category, 0.0),
                'disposals_accum': disp_acc.get(category, 0.0), 'closing_accum': c_acc.get(category, 0.0)}))
        self.line_ids.unlink()
        self.write({'line_ids': commands, 'computed': True})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
                'name': _('ความเคลื่อนไหวทรัพย์สิน')}


class BuzAssetRollforwardLine(models.TransientModel):
    _name = 'buz.asset.rollforward.line'
    _description = 'รายการความเคลื่อนไหวทรัพย์สิน'

    wizard_id = fields.Many2one('buz.asset.rollforward.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')
    category_id = fields.Many2one('buz.asset.category', string='หมวดหมู่')
    opening_cost = fields.Monetary(currency_field='currency_id', string='ราคาทุนต้นงวด')
    additions = fields.Monetary(currency_field='currency_id', string='เพิ่มขึ้น')
    disposals_cost = fields.Monetary(currency_field='currency_id', string='จำหน่าย')
    closing_cost = fields.Monetary(currency_field='currency_id', string='ราคาทุนปลายงวด')
    opening_accum = fields.Monetary(currency_field='currency_id', string='ค่าเสื่อมสะสมต้นงวด')
    depreciation = fields.Monetary(currency_field='currency_id', string='ค่าเสื่อมราคาในงวด')
    disposals_accum = fields.Monetary(currency_field='currency_id', string='ตัดค่าเสื่อมสะสมจากการจำหน่าย')
    closing_accum = fields.Monetary(currency_field='currency_id', string='ค่าเสื่อมสะสมปลายงวด')
    net_book_value = fields.Monetary(currency_field='currency_id', compute='_compute_check', string='มูลค่าตามบัญชีปลายงวด')
    cost_check = fields.Monetary(
        currency_field='currency_id', compute='_compute_check',
        help="ราคาทุนปลายงวด - (ต้นงวด + เพิ่ม - จำหน่าย) ควรเป็นศูนย์ ถ้าไม่ใช่แสดงว่ามีรายการที่ไม่เข้ากับสูตร",
        string='ผลต่างตรวจสอบราคาทุน')
    accum_check = fields.Monetary(
        currency_field='currency_id', compute='_compute_check', string='ผลต่างตรวจสอบค่าเสื่อมสะสม')

    @api.depends('opening_cost', 'additions', 'disposals_cost', 'closing_cost', 'opening_accum', 'depreciation',
                 'disposals_accum', 'closing_accum')
    def _compute_check(self):
        for line in self:
            line.net_book_value = line.closing_cost - line.closing_accum
            line.cost_check = line.closing_cost - (line.opening_cost + line.additions - line.disposals_cost)
            line.accum_check = line.closing_accum - (line.opening_accum + line.depreciation - line.disposals_accum)


# ----------------------------------------------------------------------
# Ageing
# ----------------------------------------------------------------------
AGE_BUCKETS = [
    ('lt1', 'ไม่เกิน 1 ปี', 0, 1),
    ('1to3', '1 - 3 ปี', 1, 3),
    ('3to5', '3 - 5 ปี', 3, 5),
    ('5to10', '5 - 10 ปี', 5, 10),
    ('gt10', 'มากกว่า 10 ปี', 10, None),
]


class BuzAssetAgeingWizard(models.TransientModel):
    _name = 'buz.asset.ageing.wizard'
    _inherit = 'buz.asset.report.base'
    _description = 'อายุทรัพย์สิน'

    date_to = fields.Date(required=True, default=fields.Date.context_today, string='ณ วันที่')
    line_ids = fields.One2many('buz.asset.ageing.line', 'wizard_id', readonly=True, string='รายการ')
    computed = fields.Boolean(readonly=True)

    def action_compute(self):
        self._check_company_access()
        ledger = AssetLedger(self.env, self.company_id, self.date_to)
        costs, accums = ledger.cost_by_asset(), ledger.accumulated_by_asset()
        buckets = {key: {'label': label, 'assets': self.env['buz.asset'], 'cost': 0.0, 'accum': 0.0}
                   for key, label, _lo, _hi in AGE_BUCKETS}
        for asset, cost in costs.items():
            age_days = (self.date_to - asset.in_service_date).days
            years = age_days / 365.25
            for key, _label, low, high in AGE_BUCKETS:
                if years >= low and (high is None or years < high):
                    bucket = buckets[key]
                    bucket['assets'] |= asset
                    bucket['cost'] += cost
                    bucket['accum'] += accums.get(asset, 0.0)
                    break
        commands = [Command.create({
            'sequence': index, 'bucket': data['label'], 'asset_count': len(data['assets']),
            'cost': data['cost'], 'accumulated': data['accum'], 'asset_ids': [Command.set(data['assets'].ids)]})
            for index, data in enumerate(buckets.values())]
        self.line_ids.unlink()
        self.write({'line_ids': commands, 'computed': True})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
                'name': _('อายุทรัพย์สิน')}


class BuzAssetAgeingLine(models.TransientModel):
    _name = 'buz.asset.ageing.line'
    _description = 'รายการอายุทรัพย์สิน'
    _order = 'sequence'

    wizard_id = fields.Many2one('buz.asset.ageing.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')
    sequence = fields.Integer()
    bucket = fields.Char(string='ช่วงอายุ (นับจากวันที่เริ่มใช้งาน)')
    asset_count = fields.Integer(string='จำนวน')
    cost = fields.Monetary(currency_field='currency_id', string='ราคาทุน')
    accumulated = fields.Monetary(currency_field='currency_id', string='ค่าเสื่อมสะสม (ลงบัญชีแล้ว)')
    book_value = fields.Monetary(currency_field='currency_id', compute='_compute_book_value', string='มูลค่าตามบัญชี')
    asset_ids = fields.Many2many('buz.asset', 'buz_asset_ageing_line_asset_rel', 'line_id', 'asset_id')

    @api.depends('cost', 'accumulated')
    def _compute_book_value(self):
        for line in self:
            line.book_value = line.cost - line.accumulated

    def action_open_assets(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'buz.asset', 'view_mode': 'tree,form',
                'name': self.bucket, 'domain': [('id', 'in', self.asset_ids.ids)]}
