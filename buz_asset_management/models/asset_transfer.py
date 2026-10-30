# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

CUSTODY_FIELDS = ('employee_id', 'department_id', 'location_id')
GUARDED = ('state', 'from_employee_id', 'from_department_id', 'from_location_id', 'approver_id',
           'completer_id', 'acknowledged_by_id', 'acknowledged_date', 'done_date')


class BuzAssetTransfer(models.Model):
    """Change of custodian, department or location of one asset.

    The 'from' values are a snapshot taken when the request is created and are
    never rewritten; a completed transfer is a read-only historical event.
    Inter-company transfers are out of scope (needs its own accounting flow).
    """
    _name = 'buz.asset.transfer'
    _description = 'การโอนย้ายทรัพย์สิน'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'effective_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(readonly=True, copy=False, default='/', string='เลขที่')
    asset_id = fields.Many2one(
        'buz.asset', required=True, index=True, tracking=True, check_company=True,
        ondelete='restrict', string='ทรัพย์สิน')
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company, string='บริษัท')
    effective_date = fields.Date(
        required=True, default=fields.Date.context_today, tracking=True, string='วันที่มีผล')
    reason = fields.Text(required=True, string='เหตุผล')

    from_employee_id = fields.Many2one('hr.employee', readonly=True, copy=False, string='ผู้ถือครองเดิม')
    from_department_id = fields.Many2one('hr.department', readonly=True, copy=False, string='แผนกเดิม')
    from_location_id = fields.Many2one('buz.asset.location', readonly=True, copy=False, string='สถานที่เดิม')
    to_employee_id = fields.Many2one('hr.employee', check_company=True, tracking=True, string='ผู้ถือครองใหม่')
    to_department_id = fields.Many2one('hr.department', check_company=True, tracking=True, string='แผนกใหม่')
    to_location_id = fields.Many2one('buz.asset.location', check_company=True, tracking=True, string='สถานที่ใหม่')

    requestor_id = fields.Many2one(
        'res.users', readonly=True, copy=False, default=lambda self: self.env.user, string='ผู้ขอ')
    approver_id = fields.Many2one('res.users', readonly=True, copy=False, string='ผู้อนุมัติ')
    completer_id = fields.Many2one('res.users', readonly=True, copy=False, string='ผู้ดำเนินการ')
    done_date = fields.Datetime(readonly=True, copy=False, string='ดำเนินการเมื่อ')
    acknowledged_by_id = fields.Many2one('res.users', readonly=True, copy=False, string='ผู้รับทราบ')
    acknowledged_date = fields.Datetime(readonly=True, copy=False, string='รับทราบเมื่อ')

    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('submitted', 'ส่งขออนุมัติแล้ว'),
        ('approved', 'อนุมัติแล้ว'),
        ('done', 'โอนย้ายแล้ว'),
        ('rejected', 'ไม่อนุมัติ'),
        ('cancelled', 'ยกเลิก'),
    ], required=True, default='draft', copy=False, tracking=True, string='สถานะ')

    # ------------------------------------------------------------------
    @api.onchange('asset_id')
    def _onchange_asset_id(self):
        asset = self.asset_id
        self.to_employee_id, self.to_department_id, self.to_location_id = (
            asset.employee_id, asset.department_id, asset.location_id)

    def _snapshot_vals(self, asset):
        return {'from_employee_id': asset.employee_id.id, 'from_department_id': asset.department_id.id,
                'from_location_id': asset.location_id.id}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.su and (any(k in vals for k in GUARDED if k != 'state')
                                    or vals.get('state', 'draft') != 'draft'):
                raise AccessError(_("ฟิลด์สถานะและข้อมูลเดิมเปลี่ยนได้ผ่านขั้นตอนการทำงาน (workflow) เท่านั้น"))
            asset = self.env['buz.asset'].browse(vals['asset_id'])
            company = asset.company_id
            vals['company_id'] = company.id
            vals.update(self._snapshot_vals(asset))
            # An empty 'to' value means "no change" only when it was left unset on create.
            for custody in CUSTODY_FIELDS:
                vals.setdefault('to_' + custody, asset[custody].id)
            vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('buz.asset.transfer') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if any(k in vals for k in GUARDED):
                raise AccessError(_("ฟิลด์สถานะและข้อมูลเดิมเปลี่ยนได้ผ่านขั้นตอนการทำงาน (workflow) เท่านั้น"))
            if any(t.state != 'draft' for t in self):
                raise UserError(_("แก้ไขได้เฉพาะการโอนย้ายที่เป็นร่าง"))
            if 'asset_id' in vals:
                raise UserError(_("เปลี่ยนทรัพย์สินของการโอนย้ายไม่ได้ กรุณาสร้างรายการใหม่"))
        return super().write(vals)

    def unlink(self):
        if any(t.state not in ('draft', 'cancelled') for t in self):
            raise UserError(_("ลบได้เฉพาะการโอนย้ายที่เป็นร่างหรือยกเลิกแล้ว"))
        return super().unlink()

    @api.constrains('asset_id', 'state')
    def _check_one_open_transfer(self):
        for transfer in self.filtered(lambda t: t.state in ('draft', 'submitted', 'approved')):
            if self.search_count([('asset_id', '=', transfer.asset_id.id), ('id', '!=', transfer.id),
                                  ('state', 'in', ('draft', 'submitted', 'approved'))]):
                raise ValidationError(_(
                    "ทรัพย์สิน %s มีการโอนย้ายที่ยังไม่เสร็จอยู่แล้ว", transfer.asset_id.display_name))

    def _has_change(self):
        self.ensure_one()
        return any(self['to_' + f] != self['from_' + f] for f in CUSTODY_FIELDS)

    # ------------------------------------------------------------------
    def _require_group(self, xmlid):
        if not self.env.user.has_group(xmlid):
            raise AccessError(_("คุณไม่มีสิทธิ์ทำรายการนี้"))

    def _require_state(self, *states):
        for transfer in self:
            if transfer.state not in states:
                raise UserError(_("การโอนย้าย %(name)s ต้องอยู่ในสถานะ %(states)s", name=transfer.name,
                                  states=', '.join(dict(self._fields['state'].selection)[s] for s in states)))

    def _check_asset_transferable(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.approval_state != 'approved' or asset.operational_state == 'disposed':
            raise UserError(_("ทรัพย์สิน %s ต้องอนุมัติแล้วและยังไม่ถูกจำหน่าย", asset.display_name))
        if asset.company_id != self.company_id:
            raise UserError(_("โอนย้ายระหว่างบริษัทยังไม่รองรับ"))

    def action_submit(self):
        self._require_group('buz_asset_management.group_asset_officer')
        self._require_state('draft')
        for transfer in self:
            transfer._check_asset_transferable()
            if not transfer._has_change():
                raise UserError(_("การโอนย้าย %s ไม่มีการเปลี่ยนแปลงผู้ถือครอง แผนก หรือสถานที่", transfer.name))
        self.sudo().write({'state': 'submitted'})  # sudo: state guard; group checked above

    def action_approve(self):
        self._require_group('buz_asset_management.group_asset_manager')
        self._require_state('submitted')
        self.sudo().write({'state': 'approved', 'approver_id': self.env.user.id})  # sudo: state guard

    def action_reject(self):
        self._require_group('buz_asset_management.group_asset_manager')
        self._require_state('submitted')
        self.sudo().write({'state': 'rejected', 'approver_id': self.env.user.id})  # sudo: state guard

    def action_cancel(self):
        self._require_group('buz_asset_management.group_asset_officer')
        self._require_state('draft', 'submitted', 'approved')
        self.sudo().write({'state': 'cancelled'})  # sudo: state guard; group checked above

    def action_reset_to_draft(self):
        self._require_group('buz_asset_management.group_asset_manager')
        self._require_state('rejected', 'cancelled')
        self.sudo().write({'state': 'draft', 'approver_id': False})  # sudo: state guard; group checked above

    def action_acknowledge(self):
        self._require_group('buz_asset_management.group_asset_user')
        self._require_state('approved', 'done')
        self.filtered(lambda t: not t.acknowledged_by_id).sudo().write({  # sudo: guarded fields
            'acknowledged_by_id': self.env.user.id, 'acknowledged_date': fields.Datetime.now()})

    def action_done(self):
        self._require_group('buz_asset_management.group_asset_officer')
        self._require_state('approved')
        for transfer in self:
            transfer._check_asset_transferable()
            asset = transfer.asset_id
            # Stale check: the asset moved since the request snapshot, so the "from" history would be wrong.
            if any(asset[f] != transfer['from_' + f] for f in CUSTODY_FIELDS):
                raise UserError(_(
                    "ผู้ถือครอง แผนก หรือสถานที่ของ %s เปลี่ยนไปจากตอนที่ขอโอนย้าย กรุณายกเลิกแล้วสร้างรายการใหม่",
                    asset.display_name))
            if not transfer._has_change():
                raise UserError(_("การโอนย้าย %s ไม่มีการเปลี่ยนแปลง", transfer.name))
            # sudo: custody fields of an approved asset are only changed through a transfer.
            asset.sudo().write({f: transfer['to_' + f].id for f in CUSTODY_FIELDS})
            asset.sudo().message_post(
                author_id=self.env.user.partner_id.id,
                body=_("โอนย้าย %(name)s: ผู้ถือครอง %(oe)s → %(ne)s, แผนก %(od)s → %(nd)s, สถานที่ %(ol)s → %(nl)s",
                       name=transfer.name,
                       oe=transfer.from_employee_id.name or '-', ne=transfer.to_employee_id.name or '-',
                       od=transfer.from_department_id.name or '-', nd=transfer.to_department_id.name or '-',
                       ol=transfer.from_location_id.display_name or '-',
                       nl=transfer.to_location_id.display_name or '-'))
        self.sudo().write({'state': 'done', 'completer_id': self.env.user.id, 'done_date': fields.Datetime.now()})
