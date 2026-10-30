# -*- coding: utf-8 -*-
import json
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services.depreciation import compute_straight_line_schedule

# State fields change only through the action_* methods below. Direct
# create/write of these fields by a non-superuser (including RPC) is refused.
STATE_DEFAULTS = {
    'approval_state': 'draft',
    'operational_state': 'not_in_service',
    'accounting_state': 'not_capitalized',
}
STATE_FIELDS = tuple(STATE_DEFAULTS)
# Custody of an approved asset changes only through buz.asset.transfer (keeps history).
CUSTODY_FIELDS_GUARD = {'employee_id', 'department_id', 'location_id'}


class BuzAsset(models.Model):
    _name = 'buz.asset'
    _description = 'ทรัพย์สิน'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'code desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True, string='ชื่อ')
    code = fields.Char(
        string='รหัสทรัพย์สิน', readonly=True, copy=False, default='/', index=True, tracking=True)
    active = fields.Boolean(default=True, string='เปิดใช้งาน')
    company_id = fields.Many2one(
        'res.company', required=True, index=True, tracking=True,
        default=lambda self: self.env.company, string='บริษัท')
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True, readonly=True, string='สกุลเงิน')
    category_id = fields.Many2one(
        'buz.asset.category', required=True, tracking=True, check_company=True, string='หมวดหมู่')
    description = fields.Text(string='รายละเอียด')
    image_1920 = fields.Image(string='รูปภาพ 1920')

    source_type = fields.Selection([
        ('vendor_bill', 'ใบแจ้งหนี้ผู้ขาย'),
        ('manual', 'บันทึกเอง'),
        ('opening_balance', 'ยอดยกมา'),
        ('donation', 'ได้รับบริจาค'),
        ('self_constructed', 'ก่อสร้างเอง'),
        ('other', 'อื่นๆ'),
    ], required=True, default='manual', tracking=True, string='ประเภทที่มา')
    source_ref = fields.Char(string='เหตุผล/เอกสารอ้างอิงของที่มา')
    vendor_id = fields.Many2one('res.partner', string='ผู้ขาย', check_company=True)
    source_move_id = fields.Many2one(
        'account.move', string='ใบแจ้งหนี้ต้นทาง', readonly=True, copy=False, index=True, check_company=True)
    acquisition_ids = fields.One2many('buz.asset.acquisition', 'asset_id', string='การจัดสรรจากใบแจ้งหนี้', readonly=True)

    purchase_date = fields.Date(string='วันที่ได้มา', tracking=True)
    in_service_date = fields.Date(tracking=True, string='วันที่เริ่มใช้งาน')
    depreciation_start_date = fields.Date(string='วันที่เริ่มคิดค่าเสื่อมราคา')
    gross_cost = fields.Monetary(currency_field='currency_id', tracking=True, string='ราคาทุน')
    residual_value = fields.Monetary(currency_field='currency_id', tracking=True, string='มูลค่าซาก')
    depreciable_base = fields.Monetary(
        currency_field='currency_id', compute='_compute_depreciable_base', store=True, string='มูลค่าที่ต้องคิดค่าเสื่อมราคา')
    useful_life_months = fields.Integer(tracking=True, string='อายุการใช้งาน (เดือน)')
    depreciation_method = fields.Selection(
        [('straight_line', 'เส้นตรง')], required=True, default='straight_line', string='วิธีคิดค่าเสื่อมราคา')
    depreciation_frequency = fields.Selection(
        [('monthly', 'รายเดือน')], required=True, default='monthly', string='ความถี่การตัดค่าเสื่อมราคา')

    department_id = fields.Many2one('hr.department', check_company=True, tracking=True, string='แผนก')
    employee_id = fields.Many2one('hr.employee', string='ผู้ถือครอง', check_company=True, tracking=True)
    location_id = fields.Many2one('buz.asset.location', check_company=True, tracking=True, string='สถานที่ตั้ง')
    parent_asset_id = fields.Many2one(
        'buz.asset', string='ทรัพย์สินหลัก', index=True, ondelete='restrict', check_company=True)
    coverage_ids = fields.One2many('buz.asset.coverage', 'asset_id', string='การรับประกัน/ประกันภัย')
    warranty_end_date = fields.Date(compute='_compute_coverage_dates', string='ประกันสินค้าสิ้นสุด')
    insurance_end_date = fields.Date(compute='_compute_coverage_dates', string='ประกันภัยสิ้นสุด')
    maintenance_ids = fields.One2many('buz.asset.maintenance', 'asset_id', string='ประวัติการบำรุงรักษา', readonly=True)
    transfer_ids = fields.One2many('buz.asset.transfer', 'asset_id', string='ประวัติการโอนย้าย', readonly=True)
    child_asset_ids = fields.One2many('buz.asset', 'parent_asset_id', string='ส่วนประกอบ')

    serial_number = fields.Char(string='หมายเลขเครื่อง')
    manufacturer = fields.Char(string='ผู้ผลิต')
    model_name = fields.Char(string='รุ่น')
    barcode = fields.Char(copy=False, string='บาร์โค้ด')
    qr_token = fields.Char(
        copy=False, readonly=True, index=True, default=lambda self: uuid.uuid4().hex,
        help="รหัสลับสำหรับป้าย QR ใช้เข้าถึงข้อมูลด้วยตัวเองไม่ได้", string='โทเคน QR')

    depreciation_line_ids = fields.One2many(
        'buz.asset.depreciation.line', 'asset_id', string='ตารางค่าเสื่อมราคา', readonly=True)

    accumulated_depreciation = fields.Monetary(
        currency_field='currency_id', compute='_compute_book_value', store=True,
        help="ผลรวมค่าเสื่อมราคาที่ลงบัญชีแล้วเท่านั้น (ไม่รวมตามแผน)", string='ค่าเสื่อมราคาสะสม (ลงบัญชีแล้ว)')
    book_value = fields.Monetary(
        currency_field='currency_id', compute='_compute_book_value', store=True,
        help="ราคาทุน - ค่าเสื่อมราคาสะสมที่ลงบัญชีแล้ว (ทรัพย์สินที่จำหน่ายแล้วเป็นศูนย์)", string='มูลค่าตามบัญชี')

    approval_state = fields.Selection([
        ('draft', 'ร่าง'),
        ('submitted', 'ส่งขออนุมัติแล้ว'),
        ('approved', 'อนุมัติแล้ว'),
    ], required=True, default='draft', copy=False, tracking=True, string='สถานะการอนุมัติ')
    operational_state = fields.Selection([
        ('not_in_service', 'ยังไม่เริ่มใช้งาน'),
        ('in_service', 'อยู่ระหว่างใช้งาน'),
        ('under_maintenance', 'อยู่ระหว่างซ่อมบำรุง'),
        ('missing', 'สูญหาย'),
        ('on_loan', 'อยู่ระหว่างยืม'),
        ('disposed', 'จำหน่ายแล้ว'),
    ], required=True, default='not_in_service', copy=False, tracking=True, string='สถานะการใช้งาน')
    accounting_state = fields.Selection([
        ('not_capitalized', 'ยังไม่บันทึกเป็นสินทรัพย์'),
        ('capitalized', 'บันทึกเป็นสินทรัพย์แล้ว'),
        ('disposed', 'จำหน่ายแล้ว'),
    ], required=True, default='not_capitalized', copy=False, tracking=True, string='สถานะทางบัญชี')

    _sql_constraints = [
        ('code_company_uniq', 'unique(company_id, code)',
         'รหัสทรัพย์สินต้องไม่ซ้ำกันภายในบริษัท'),
        ('qr_token_uniq', 'unique(qr_token)', 'โทเคน QR ต้องไม่ซ้ำกัน'),
        ('gross_cost_non_negative', 'CHECK(gross_cost >= 0)', 'ราคาทุนต้องไม่ติดลบ'),
        ('residual_non_negative', 'CHECK(residual_value >= 0)',
         'มูลค่าซากต้องไม่ติดลบ'),
        ('residual_le_gross', 'CHECK(residual_value <= gross_cost)',
         'มูลค่าซากต้องไม่เกินราคาทุน'),
        ('useful_life_non_negative', 'CHECK(useful_life_months >= 0)',
         'อายุการใช้งานต้องไม่ติดลบ'),
    ]

    # ------------------------------------------------------------------
    # Computes / onchange / constraints
    # ------------------------------------------------------------------
    @api.depends('gross_cost', 'residual_value')
    def _compute_depreciable_base(self):
        for asset in self:
            asset.depreciable_base = max(0.0, asset.gross_cost - asset.residual_value)

    @api.depends('gross_cost', 'operational_state',
                 'depreciation_line_ids.state', 'depreciation_line_ids.planned_amount')
    def _compute_book_value(self):
        for asset in self:
            posted = asset.depreciation_line_ids.filtered(lambda l: l.state == 'posted')
            asset.accumulated_depreciation = sum(posted.mapped('planned_amount'))
            asset.book_value = 0.0 if asset.operational_state == 'disposed' else (
                asset.gross_cost - asset.accumulated_depreciation)

    @api.depends('coverage_ids.date_start', 'coverage_ids.date_end', 'coverage_ids.coverage_type',
                 'coverage_ids.active')
    @api.depends_context('uid')
    def _compute_coverage_dates(self):
        today = fields.Date.context_today(self)
        for asset in self:
            current = asset.coverage_ids.filtered(lambda c: c.date_start <= today <= c.date_end)
            warranties = current.filtered(lambda c: c.coverage_type == 'warranty')
            policies = current.filtered(lambda c: c.coverage_type == 'insurance')
            asset.warranty_end_date = max(warranties.mapped('date_end')) if warranties else False
            asset.insurance_end_date = max(policies.mapped('date_end')) if policies else False

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id and not self.useful_life_months:
            self.useful_life_months = self.category_id.useful_life_months

    @api.constrains('parent_asset_id')
    def _check_parent_recursion(self):
        if not self._check_recursion(parent='parent_asset_id'):
            raise ValidationError(_('ทรัพย์สินไม่สามารถเป็นทรัพย์สินหลักของตัวเองได้'))

    @api.constrains('depreciable_base', 'useful_life_months')
    def _check_useful_life(self):
        for asset in self:
            if asset.depreciable_base > 0 and asset.useful_life_months <= 0:
                raise ValidationError(_(
                    "ทรัพย์สิน %s มีมูลค่าที่ต้องคิดค่าเสื่อมราคา อายุการใช้งานจึงต้องมากกว่าศูนย์", asset.display_name))

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.su:
                for field in STATE_FIELDS:
                    if field in vals and vals[field] != STATE_DEFAULTS[field]:
                        raise AccessError(_("ฟิลด์สถานะเปลี่ยนได้ผ่านขั้นตอนการทำงาน (workflow) เท่านั้น"))
            company = (self.env['res.company'].browse(vals['company_id'])
                       if vals.get('company_id') else self.env.company)
            code = self.env['ir.sequence'].with_company(company).next_by_code('buz.asset')
            if not code:
                raise UserError(_("ยังไม่ได้ตั้งค่าลำดับเลขที่ที่มีรหัส 'buz.asset'"))
            vals['code'] = code
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if any(field in vals for field in STATE_FIELDS):
                raise AccessError(_("ฟิลด์สถานะเปลี่ยนได้ผ่านขั้นตอนการทำงาน (workflow) เท่านั้น"))
            if 'code' in vals:
                raise AccessError(_("ไม่สามารถเปลี่ยนรหัสทรัพย์สินได้"))
            if CUSTODY_FIELDS_GUARD & set(vals):
                for asset in self.filtered(lambda a: a.approval_state == 'approved'):
                    if any(vals[f] != (asset[f].id or False) for f in CUSTODY_FIELDS_GUARD & set(vals)):
                        raise UserError(_(
                            "ทรัพย์สิน %s อนุมัติแล้ว ผู้ถือครอง แผนก และสถานที่เปลี่ยนได้ผ่านการโอนย้ายเท่านั้น",
                            asset.display_name))
        return super().write(vals)

    def unlink(self):
        for asset in self:
            if asset.approval_state != 'draft':
                raise UserError(_(
                    "ทรัพย์สิน %s ไม่ได้อยู่ในสถานะร่างแล้ว จึงลบไม่ได้ กรุณาเก็บถาวรแทน",
                    asset.display_name))
        return super().unlink()

    # ------------------------------------------------------------------
    # Workflow (permission + state validated server-side)
    # ------------------------------------------------------------------
    def _require_group(self, xmlid):
        if not self.env.user.has_group(xmlid):
            raise AccessError(_("คุณไม่มีสิทธิ์ทำรายการนี้"))

    def _require_approval_state(self, expected):
        for asset in self:
            if asset.approval_state != expected:
                raise UserError(_(
                    "ทรัพย์สิน %(asset)s ต้องอยู่ในสถานะ '%(state)s' จึงจะทำรายการนี้ได้",
                    asset=asset.display_name, state=expected))

    def action_submit(self):
        self._require_group('buz_asset_management.group_asset_officer')
        self._require_approval_state('draft')
        self.sudo().write({'approval_state': 'submitted'})  # sudo: state write guard; group checked above

    def action_approve(self):
        self._require_group('buz_asset_management.group_asset_manager')
        self._require_approval_state('submitted')
        self.sudo().write({'approval_state': 'approved'})  # sudo: state write guard; group checked above

    def action_reset_to_draft(self):
        self._require_group('buz_asset_management.group_asset_manager')
        for asset in self:
            if asset.approval_state not in ('submitted', 'approved'):
                raise UserError(_("รีเซ็ตเป็นร่างได้เฉพาะทรัพย์สินที่ส่งขออนุมัติหรืออนุมัติแล้วเท่านั้น"))
            if asset.operational_state != 'not_in_service' or asset.accounting_state != 'not_capitalized':
                raise UserError(_(
                    "ทรัพย์สิน %s เริ่มใช้งานหรือบันทึกเป็นสินทรัพย์แล้ว จึงรีเซ็ตไม่ได้",
                    asset.display_name))
        self.sudo().write({'approval_state': 'draft'})  # sudo: state write guard; group checked above

    # ------------------------------------------------------------------
    # QR label
    # ------------------------------------------------------------------
    def _qr_payload(self):
        """Label content: login-protected URL with the opaque token; no accounting data."""
        self.ensure_one()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        return '%s/buz_asset/qr/%s' % (base.rstrip('/'), self.qr_token)

    def _qr_image_src(self, size=140):
        from werkzeug.urls import url_quote
        self.ensure_one()
        return '/report/barcode/?barcode_type=QR&value=%s&width=%s&height=%s' % (
            url_quote(self._qr_payload(), safe=''), size, size)

    @api.model
    def _qr_target_url(self, token):
        """Where a scanned token should lead the CURRENT user, or False.

        Runs with the caller's rights: an asset the user cannot read returns
        False exactly like an unknown token. A pending audit count for the
        asset takes priority so a phone scan lands on the count form."""
        if not token:
            return False
        try:
            asset = self.search([('qr_token', '=', token)], limit=1)
            if not asset:
                return False
            line = self.env['buz.asset.audit.line'].search([
                ('asset_id', '=', asset.id), ('audit_id.state', '=', 'in_progress'),
                ('result', '=', 'not_checked')], limit=1)
        except AccessError:
            return False
        if line:
            return '/web#id=%s&model=buz.asset.audit.line&view_type=form' % line.id
        return '/web#id=%s&model=buz.asset&view_type=form' % asset.id

    def _has_warranty_on(self, date):
        self.ensure_one()
        return bool(self.coverage_ids.filtered(
            lambda c: c.coverage_type == 'warranty' and c.date_start <= date <= c.date_end))

    def action_new_maintenance(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'buz.asset.maintenance', 'view_mode': 'form',
                'name': _('งานบำรุงรักษา'), 'context': {'default_asset_id': self.id}}

    def action_new_transfer(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'buz.asset.transfer', 'view_mode': 'form',
            'name': _('โอนย้ายทรัพย์สิน'), 'target': 'current',
            'context': {'default_asset_id': self.id, 'default_to_employee_id': self.employee_id.id,
                        'default_to_department_id': self.department_id.id,
                        'default_to_location_id': self.location_id.id}}

    def action_put_in_service(self):
        self._require_group('buz_asset_management.group_asset_officer')
        self._require_approval_state('approved')
        for asset in self:
            if asset.operational_state != 'not_in_service':
                raise UserError(_("ทรัพย์สิน %s เริ่มใช้งานแล้ว", asset.display_name))
            if not asset.in_service_date:
                raise UserError(_("กรุณาระบุวันที่เริ่มใช้งานของ %s ก่อน", asset.display_name))
        self.sudo().write({'operational_state': 'in_service'})  # sudo: state write guard; group checked above

    def action_capitalize(self):
        """Mark the asset as capitalized. No journal entry: cost is already in the GL
        (vendor bill, opening balance or manual registration is register-only)."""
        self._require_group('buz_asset_management.group_asset_accountant')
        self._require_approval_state('approved')
        for asset in self:
            category = asset.category_id
            if asset.operational_state != 'in_service':
                raise UserError(_("ทรัพย์สิน %s ต้องเริ่มใช้งานก่อนจึงจะบันทึกเป็นสินทรัพย์ได้", asset.display_name))
            if asset.accounting_state != 'not_capitalized':
                raise UserError(_("ทรัพย์สิน %s บันทึกเป็นสินทรัพย์แล้ว", asset.display_name))
            if not (category.asset_account_id and category.depreciation_account_id
                    and category.expense_account_id and category.journal_id):
                raise UserError(_("หมวดหมู่ %s ยังตั้งค่าบัญชีและสมุดรายวันไม่ครบ", category.display_name))
        self.sudo().write({'accounting_state': 'capitalized'})  # sudo: state write guard; group checked above

    # ------------------------------------------------------------------
    # Depreciation schedule (plan only; no journal entries)
    # ------------------------------------------------------------------
    def action_compute_schedule(self):
        """(Re)compute the planned straight-line schedule."""
        self._require_group('buz_asset_management.group_asset_accountant')
        for asset in self:
            asset._compute_schedule()

    def _compute_schedule(self):
        self.ensure_one()
        if self.operational_state == 'disposed':
            raise UserError(_("ทรัพย์สิน %s ถูกจำหน่ายแล้ว จึงไม่มีตารางค่าเสื่อมราคา", self.display_name))
        start_date = self.depreciation_start_date or self.in_service_date
        if not start_date:
            raise UserError(_(
                "กรุณาระบุวันที่เริ่มใช้งานหรือวันที่เริ่มคิดค่าเสื่อมราคาของ %s ก่อน", self.display_name))
        if self.useful_life_months <= 0:
            raise UserError(_("กรุณาระบุอายุการใช้งานของ %s ก่อน", self.display_name))
        if self.depreciation_line_ids.filtered(lambda line: line.state != 'planned'):
            raise UserError(_(
                "ทรัพย์สิน %s มีรายการเกินสถานะวางแผนแล้ว กรุณาใช้การกลับรายการหรือปรับปรุงแทนการคำนวณใหม่", self.display_name))

        rows = compute_straight_line_schedule(
            self.depreciable_base, self.useful_life_months, start_date, self.currency_id.round)
        version = max(self.depreciation_line_ids.mapped('calculation_version') or [0]) + 1
        snapshot = json.dumps({
            'depreciable_base': self.depreciable_base,
            'useful_life_months': self.useful_life_months,
            'start_date': fields.Date.to_string(start_date),
            'convention': 'full_month',
            'method': self.depreciation_method,
        }, sort_keys=True)
        # sudo: schedule lines have no direct write access; group checked in action.
        Line = self.env['buz.asset.depreciation.line'].sudo()
        self.depreciation_line_ids.sudo().unlink()
        Line.create([{
            'asset_id': self.id,
            'sequence': row['sequence'],
            'name': '%s (%s/%s)' % (self.code, row['sequence'], len(rows)),
            'depreciation_date': row['depreciation_date'],
            'period_start': row['period_start'],
            'period_end': row['period_end'],
            'planned_amount': row['amount'],
            'remaining_after': row['remaining_after'],
            'idempotency_key': '%s:%s:depreciation' % (self.id, row['sequence']),
            'calculation_version': version,
            'calculation_snapshot': snapshot,
        } for row in rows])
        # sudo: accountants have read-only access to the asset, which is not enough
        # to post; authorship stays with the acting user.
        self.sudo().message_post(
            author_id=self.env.user.partner_id.id,
            body=_("คำนวณตารางค่าเสื่อมราคาแล้ว: %(count)s งวด เวอร์ชัน %(version)s",
                   count=len(rows), version=version))
