# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class BuzAssetDashboard(models.TransientModel):
    """Live KPI form. Nothing is stored; every figure is read on open under the
    user's own access rights and the companies selected in the switcher."""
    _name = 'buz.asset.dashboard'
    _description = 'แดชบอร์ดทรัพย์สิน'

    company_ids = fields.Many2many('res.company', compute='_compute_kpis', string='บริษัท')
    currency_id = fields.Many2one('res.currency', compute='_compute_kpis')
    asset_count = fields.Integer(compute='_compute_kpis', string='จำนวนทรัพย์สิน')
    total_cost = fields.Monetary(compute='_compute_kpis', string='ราคาทุนรวม')
    accumulated_depreciation = fields.Monetary(compute='_compute_kpis', string='ค่าเสื่อมราคาสะสม')
    book_value = fields.Monetary(compute='_compute_kpis', string='มูลค่าตามบัญชี')
    pending_approval_count = fields.Integer(compute='_compute_kpis', string='รออนุมัติ')
    due_depreciation_count = fields.Integer(compute='_compute_kpis', string='ค่าเสื่อมครบกำหนดยังไม่ลงบัญชี')
    exception_count = fields.Integer(compute='_compute_kpis', string='ค่าเสื่อมติดข้อยกเว้น')
    pending_disposal_count = fields.Integer(compute='_compute_kpis', string='การจำหน่ายที่ยังไม่ลงบัญชี')
    audit_rate = fields.Float(compute='_compute_kpis', string='อัตราตรวจนับ (%) ของรอบที่กำลังดำเนินการ')
    maintenance_open_count = fields.Integer(compute='_compute_kpis', string='งานบำรุงรักษาที่ยังไม่เสร็จ')
    maintenance_overdue_count = fields.Integer(compute='_compute_kpis', string='งานบำรุงรักษาเลยกำหนด')
    coverage_expiring_count = fields.Integer(compute='_compute_kpis', string='การรับประกัน/ประกันใกล้หมดอายุ')
    coverage_expired_count = fields.Integer(compute='_compute_kpis', string='การรับประกัน/ประกันหมดอายุ')
    audit_open_count = fields.Integer(compute='_compute_kpis', string='รอบตรวจนับที่กำลังดำเนินการ')

    # Active, not disposed assets are the live register.
    def _live_domain(self):
        return [('operational_state', '!=', 'disposed'), ('approval_state', '=', 'approved')]

    def _due_domain(self):
        return [('state', '=', 'planned'), ('depreciation_date', '<=', fields.Date.context_today(self))]

    @api.depends_context('allowed_company_ids')
    def _compute_kpis(self):
        Asset, Line, Disposal = (self.env['buz.asset'], self.env['buz.asset.depreciation.line'],
                                 self.env['buz.asset.disposal'])
        companies = self.env.companies
        for dash in self:
            dash.company_ids = companies
            dash.currency_id = self.env.company.currency_id
            totals = Asset.read_group(self._live_domain(), ['gross_cost:sum', 'accumulated_depreciation:sum',
                                                            'book_value:sum'], [])
            row = totals[0] if totals else {}
            dash.asset_count = Asset.search_count(self._live_domain())
            dash.total_cost = row.get('gross_cost') or 0.0
            dash.accumulated_depreciation = row.get('accumulated_depreciation') or 0.0
            dash.book_value = row.get('book_value') or 0.0
            dash.pending_approval_count = Asset.search_count([('approval_state', '=', 'submitted')])
            dash.due_depreciation_count = Line.search_count(self._due_domain())
            dash.exception_count = Line.search_count([('state', '=', 'exception')])
            dash.pending_disposal_count = Disposal.search_count([('state', 'in', ('draft', 'approved'))])
            Cov = self.env['buz.asset.coverage']
            dash.coverage_expiring_count = Cov.search_count([('state', '=', 'expiring')])
            dash.coverage_expired_count = Cov.search_count([('state', '=', 'expired')])
            Maint = self.env['buz.asset.maintenance']
            dash.maintenance_open_count = Maint.search_count([('state', 'in', ('planned', 'in_progress'))])
            dash.maintenance_overdue_count = Maint.search_count(Maint._overdue_domain())
            lines = self.env['buz.asset.audit.line'].search([('audit_id.state', '=', 'in_progress')])
            checked = len(lines.filtered(lambda l: l.result != 'not_checked'))
            dash.audit_rate = 100.0 * checked / len(lines) if lines else 0.0
            dash.audit_open_count = self.env['buz.asset.audit'].search_count([('state', '=', 'in_progress')])

    @api.model
    def action_open(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'name': _('แดชบอร์ดทรัพย์สิน'),
            'view_mode': 'form', 'res_id': self.create({}).id, 'target': 'current',
            'context': {'form_view_initial_mode': 'readonly'}}

    def _open(self, name, model, domain, views='tree,form'):
        return {'type': 'ir.actions.act_window', 'name': name, 'res_model': model,
                'view_mode': views, 'domain': domain}

    def action_open_assets(self):
        return self._open(_('ทรัพย์สิน'), 'buz.asset', self._live_domain())

    def action_open_pending_approval(self):
        return self._open(_('ทรัพย์สินรออนุมัติ'), 'buz.asset', [('approval_state', '=', 'submitted')])

    def action_open_due_lines(self):
        return self._open(_('ค่าเสื่อมครบกำหนดยังไม่ลงบัญชี'), 'buz.asset.depreciation.line',
                          self._due_domain(), 'tree')

    def action_open_exception_lines(self):
        return self._open(_('ค่าเสื่อมติดข้อยกเว้น'), 'buz.asset.depreciation.line',
                          [('state', '=', 'exception')], 'tree')

    def action_open_maintenance(self):
        return self._open(_('งานบำรุงรักษาที่ยังไม่เสร็จ'), 'buz.asset.maintenance',
                          [('state', 'in', ('planned', 'in_progress'))])

    def action_open_overdue_maintenance(self):
        return self._open(_('งานบำรุงรักษาเลยกำหนด'), 'buz.asset.maintenance',
                          self.env['buz.asset.maintenance']._overdue_domain())

    def action_open_expiring_coverage(self):
        return self._open(_('การรับประกัน/ประกันใกล้หมดอายุ'), 'buz.asset.coverage', [('state', '=', 'expiring')])

    def action_open_pending_disposals(self):
        return self._open(_('การจำหน่ายที่ยังไม่ลงบัญชี'), 'buz.asset.disposal',
                          [('state', 'in', ('draft', 'approved'))])
