# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

RESULTS = [
    ('not_checked', 'ยังไม่ตรวจ'),
    ('found', 'พบ'),
    ('not_found', 'ไม่พบ'),
    ('wrong_location', 'ผิดสถานที่'),
    ('wrong_custodian', 'ผิดผู้ถือครอง'),
    ('damaged', 'ชำรุด'),
    ('retired', 'เลิกใช้/จำหน่ายแล้ว'),
]
RESOLUTIONS = [
    ('transfer', 'โอนย้าย'),
    ('corrected', 'แก้ไขข้อมูล'),
    ('investigating', 'อยู่ระหว่างสอบสวน'),
    ('disposal', 'จำหน่าย'),
    ('accepted', 'ยอมรับตามที่พบ'),
]
SNAPSHOT_FIELDS = ('expected_employee_id', 'expected_department_id', 'expected_location_id', 'asset_id', 'audit_id')
RESULT_FIELDS = ('result', 'scanned_by_id', 'scanned_date')
RESOLUTION_FIELDS = ('resolution', 'resolution_note')


class BuzAssetAudit(models.Model):
    """Physical count campaign. Expected custody is snapshotted at start and
    observations never overwrite it or the asset itself."""
    _name = 'buz.asset.audit'
    _description = 'การตรวจนับทรัพย์สิน'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(readonly=True, copy=False, default='/', string='เลขที่')
    title = fields.Char(required=True, string='ชื่อรอบการตรวจนับ')
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company, string='บริษัท')
    date = fields.Date(required=True, default=fields.Date.context_today, string='วันที่ตรวจนับ')
    responsible_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user, tracking=True, string='ผู้รับผิดชอบ')
    department_ids = fields.Many2many(
        'hr.department', 'buz_asset_audit_department_rel', 'audit_id', 'department_id',
        check_company=True, string='แผนก')
    location_ids = fields.Many2many(
        'buz.asset.location', 'buz_asset_audit_location_rel', 'audit_id', 'location_id',
        check_company=True, string='สถานที่ตั้ง')
    category_ids = fields.Many2many(
        'buz.asset.category', 'buz_asset_audit_category_rel', 'audit_id', 'category_id',
        check_company=True, string='หมวดหมู่')
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('in_progress', 'กำลังตรวจนับ'),
        ('closed', 'ปิดแล้ว'),
        ('cancelled', 'ยกเลิก'),
    ], required=True, default='draft', copy=False, tracking=True, string='สถานะ')
    snapshot_date = fields.Datetime(readonly=True, copy=False, string='เวลาที่บันทึกข้อมูลที่คาดหวัง')
    line_ids = fields.One2many('buz.asset.audit.line', 'audit_id', string='รายการ')

    line_count = fields.Integer(compute='_compute_metrics', string='จำนวนทั้งหมด')
    checked_count = fields.Integer(compute='_compute_metrics', string='ตรวจแล้ว')
    exception_count = fields.Integer(compute='_compute_metrics', string='ผิดปกติ')
    unresolved_count = fields.Integer(compute='_compute_metrics', string='ผิดปกติที่ยังไม่แก้ไข')
    completion_rate = fields.Float(compute='_compute_metrics', string='อัตราตรวจนับ (%)')

    @api.depends('line_ids.result', 'line_ids.resolution')
    def _compute_metrics(self):
        for audit in self:
            lines = audit.line_ids
            checked = lines.filtered(lambda l: l.result != 'not_checked')
            exceptions = checked.filtered(lambda l: l.result != 'found')
            audit.line_count = len(lines)
            audit.checked_count = len(checked)
            audit.exception_count = len(exceptions)
            audit.unresolved_count = len(exceptions.filtered(lambda l: not l.resolution))
            audit.completion_rate = 100.0 * len(checked) / len(lines) if lines else 0.0

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.su and ('state' in vals and vals['state'] != 'draft' or 'snapshot_date' in vals):
                raise AccessError(_("ฟิลด์สถานะเปลี่ยนได้ผ่านขั้นตอนการทำงาน (workflow) เท่านั้น"))
            company = (self.env['res.company'].browse(vals['company_id'])
                       if vals.get('company_id') else self.env.company)
            vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('buz.asset.audit') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if {'state', 'snapshot_date', 'line_ids'} & set(vals):
                raise AccessError(_("ฟิลด์สถานะและรายการเปลี่ยนได้ผ่านขั้นตอนการทำงาน (workflow) เท่านั้น"))
            scope = {'company_id', 'department_ids', 'location_ids', 'category_ids'}
            if scope & set(vals) and any(a.state != 'draft' for a in self):
                raise UserError(_("เปลี่ยนขอบเขตได้เฉพาะรอบตรวจนับที่เป็นร่าง"))
        return super().write(vals)

    def unlink(self):
        if any(a.state not in ('draft', 'cancelled') for a in self):
            raise UserError(_("ลบได้เฉพาะรอบตรวจนับที่เป็นร่างหรือยกเลิกแล้ว"))
        return super().unlink()

    def _require_group(self, xmlid):
        if not self.env.user.has_group(xmlid):
            raise AccessError(_("คุณไม่มีสิทธิ์ทำรายการนี้"))

    def _scope_domain(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id), ('approval_state', '=', 'approved'),
                  ('operational_state', '!=', 'disposed')]
        if self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))
        if self.location_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        if self.category_ids:
            domain.append(('category_id', 'in', self.category_ids.ids))
        return domain

    def action_start(self):
        self._require_group('buz_asset_management.group_asset_officer')
        for audit in self:
            if audit.state != 'draft':
                raise UserError(_("เริ่มได้เฉพาะรอบตรวจนับที่เป็นร่าง"))
            assets = self.env['buz.asset'].search(audit._scope_domain())
            if not assets:
                raise UserError(_("ไม่พบทรัพย์สินตามขอบเขตที่เลือก"))
            # sudo: lines are created only here; the expected snapshot is frozen at this point.
            self.env['buz.asset.audit.line'].sudo().create([{
                'audit_id': audit.id, 'asset_id': asset.id,
                'expected_employee_id': asset.employee_id.id,
                'expected_department_id': asset.department_id.id,
                'expected_location_id': asset.location_id.id} for asset in assets])
            audit.sudo().write({'state': 'in_progress', 'snapshot_date': fields.Datetime.now()})

    def action_close(self):
        self._require_group('buz_asset_management.group_asset_manager')
        for audit in self:
            if audit.state != 'in_progress':
                raise UserError(_("ปิดได้เฉพาะรอบตรวจนับที่กำลังดำเนินการ"))
            pending = audit.line_ids.filtered(lambda l: l.result == 'not_checked')
            if pending:
                raise UserError(_("ยังมีทรัพย์สินที่ยังไม่ตรวจ %s รายการ", len(pending)))
            if audit.unresolved_count:
                raise UserError(_("ยังมีรายการผิดปกติที่ยังไม่ระบุการแก้ไข %s รายการ", audit.unresolved_count))
        self.sudo().write({'state': 'closed'})  # sudo: state guard; group checked above

    def action_cancel(self):
        self._require_group('buz_asset_management.group_asset_manager')
        if any(a.state not in ('draft', 'in_progress') for a in self):
            raise UserError(_("ยกเลิกได้เฉพาะรอบตรวจนับที่เป็นร่างหรือกำลังดำเนินการ"))
        self.sudo().write({'state': 'cancelled'})  # sudo: state guard; group checked above

    def action_open_scan(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'buz.asset.audit.scan.wizard', 'view_mode': 'form',
                'target': 'new', 'name': _('สแกน/ค้นหาทรัพย์สิน'), 'context': {'default_audit_id': self.id}}

    def action_open_lines(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'buz.asset.audit.line', 'view_mode': 'tree,form',
                'name': _('รายการตรวจนับ'), 'domain': [('audit_id', '=', self.id)],
                'context': {'search_default_group_result': 1}}


class BuzAssetAuditLine(models.Model):
    _name = 'buz.asset.audit.line'
    _description = 'รายการตรวจนับทรัพย์สิน'
    _order = 'audit_id, id'
    _check_company_auto = True

    audit_id = fields.Many2one('buz.asset.audit', required=True, index=True, ondelete='cascade', readonly=True,
                               string='รอบตรวจนับ')
    asset_id = fields.Many2one('buz.asset', required=True, index=True, ondelete='restrict', readonly=True,
                               string='ทรัพย์สิน')
    company_id = fields.Many2one('res.company', related='audit_id.company_id', store=True, index=True,
                                 string='บริษัท')
    audit_state = fields.Selection(related='audit_id.state', string='สถานะรอบตรวจนับ')
    asset_code = fields.Char(related='asset_id.code', string='รหัส')

    expected_employee_id = fields.Many2one('hr.employee', readonly=True, string='ผู้ถือครองที่คาดหวัง')
    expected_department_id = fields.Many2one('hr.department', readonly=True, string='แผนกที่คาดหวัง')
    expected_location_id = fields.Many2one('buz.asset.location', readonly=True, string='สถานที่ที่คาดหวัง')

    actual_employee_id = fields.Many2one('hr.employee', string='ผู้ถือครองที่พบจริง')
    actual_location_id = fields.Many2one('buz.asset.location', string='สถานที่ที่พบจริง')
    notes = fields.Text(string='หมายเหตุ')
    photo = fields.Image(max_width=1024, max_height=1024, string='รูปถ่าย')

    result = fields.Selection(RESULTS, required=True, default='not_checked', readonly=True, string='ผลการตรวจ')
    scanned_by_id = fields.Many2one('res.users', readonly=True, string='ผู้ตรวจ')
    scanned_date = fields.Datetime(readonly=True, string='ตรวจเมื่อ')
    resolution = fields.Selection(RESOLUTIONS, string='การแก้ไข')
    resolution_note = fields.Text(string='รายละเอียดการแก้ไข')

    _sql_constraints = [
        ('audit_asset_uniq', 'unique(audit_id, asset_id)', 'ทรัพย์สินปรากฏได้เพียงครั้งเดียวในรอบตรวจนับ'),
    ]

    def write(self, vals):
        if not self.env.su:
            if set(SNAPSHOT_FIELDS) & set(vals) or set(RESULT_FIELDS) & set(vals):
                raise AccessError(_("ข้อมูลที่คาดหวังและผลการตรวจเปลี่ยนได้ผ่านปุ่มบันทึกผลเท่านั้น"))
            if set(RESOLUTION_FIELDS) & set(vals) and not self.env.user.has_group(
                    'buz_asset_management.group_asset_officer'):
                raise AccessError(_("เฉพาะเจ้าหน้าที่ทรัพย์สินที่ระบุการแก้ไขได้"))
            if any(line.audit_id.state != 'in_progress' for line in self):
                raise UserError(_("แก้ไขได้เฉพาะรอบตรวจนับที่กำลังดำเนินการ"))
        return super().write(vals)

    def unlink(self):
        if not self.env.su and any(line.audit_id.state != 'draft' for line in self):
            raise UserError(_("ลบรายการตรวจนับไม่ได้"))
        return super().unlink()

    def _record(self, result):
        for line in self:
            if line.audit_id.state != 'in_progress':
                raise UserError(_("บันทึกผลได้เฉพาะรอบตรวจนับที่กำลังดำเนินการ"))
            vals = {'result': result, 'scanned_by_id': self.env.user.id, 'scanned_date': fields.Datetime.now()}
            if result == 'found':
                vals.update(actual_location_id=line.expected_location_id.id,
                            actual_employee_id=line.expected_employee_id.id)
            elif result == 'wrong_location' and (
                    not line.actual_location_id or line.actual_location_id == line.expected_location_id):
                raise UserError(_("ผิดสถานที่: กรุณาระบุสถานที่ที่พบจริงให้ต่างจากที่คาดหวัง"))
            elif result == 'wrong_custodian' and (
                    not line.actual_employee_id or line.actual_employee_id == line.expected_employee_id):
                raise UserError(_("ผิดผู้ถือครอง: กรุณาระบุผู้ถือครองที่พบจริงให้ต่างจากที่คาดหวัง"))
            # sudo: result fields are write-guarded; any asset user may record a count.
            line.sudo().write(vals)

    def _require_user(self):
        if not self.env.user.has_group('buz_asset_management.group_asset_user'):
            raise AccessError(_("คุณไม่มีสิทธิ์ทำรายการนี้"))

    def action_found(self):
        self._require_user()
        self._record('found')

    def action_not_found(self):
        self._require_user()
        self._record('not_found')

    def action_wrong_location(self):
        self._require_user()
        self._record('wrong_location')

    def action_wrong_custodian(self):
        self._require_user()
        self._record('wrong_custodian')

    def action_damaged(self):
        self._require_user()
        self._record('damaged')

    def action_retired(self):
        self._require_user()
        self._record('retired')

    def action_create_transfer(self):
        """Resolve a wrong location/custodian through the normal transfer flow."""
        self.ensure_one()
        if not self.env.user.has_group('buz_asset_management.group_asset_officer'):
            raise AccessError(_("คุณไม่มีสิทธิ์ทำรายการนี้"))
        if self.result not in ('wrong_location', 'wrong_custodian'):
            raise UserError(_("สร้างการโอนย้ายได้เฉพาะรายการผิดสถานที่หรือผิดผู้ถือครอง"))
        asset = self.asset_id
        return {
            'type': 'ir.actions.act_window', 'res_model': 'buz.asset.transfer', 'view_mode': 'form',
            'name': _('โอนย้ายทรัพย์สิน'),
            'context': {'default_asset_id': asset.id,
                        'default_reason': _('ผลการตรวจนับ %s', self.audit_id.name),
                        'default_to_employee_id': (self.actual_employee_id or asset.employee_id).id,
                        'default_to_department_id': asset.department_id.id,
                        'default_to_location_id': (self.actual_location_id or asset.location_id).id}}


class BuzAssetAuditScanWizard(models.TransientModel):
    """Find the line of a campaign by asset code, barcode, serial number or QR token.
    Works with keyboard-wedge scanners and typed input; no custom JS."""
    _name = 'buz.asset.audit.scan.wizard'
    _description = 'สแกนทรัพย์สินในรอบตรวจนับ'

    audit_id = fields.Many2one('buz.asset.audit', required=True, readonly=True, string='รอบตรวจนับ')
    code = fields.Char(required=True, string='รหัสทรัพย์สิน / บาร์โค้ด / S/N')

    def action_find(self):
        self.ensure_one()
        code = (self.code or '').strip()
        # QR labels carry a URL; accept the whole URL or the bare token.
        token = code.rsplit('/', 1)[-1]
        asset = self.env['buz.asset'].search(
            ['|', '|', '|', ('code', '=', code), ('barcode', '=', code), ('serial_number', '=', code),
             ('qr_token', '=', token)], limit=2)
        line = self.env['buz.asset.audit.line'].search(
            [('audit_id', '=', self.audit_id.id), ('asset_id', 'in', asset.ids)], limit=1)
        if not line:
            raise UserError(_("ไม่พบ '%s' ในรอบตรวจนับนี้ (อาจเป็นทรัพย์สินนอกขอบเขต)", code))
        return {'type': 'ir.actions.act_window', 'res_model': 'buz.asset.audit.line', 'view_mode': 'form',
                'res_id': line.id, 'name': line.asset_id.display_name}
