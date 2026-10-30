# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class BuzAssetDepreciationLine(models.Model):
    """One planned depreciation period of an asset (custom backend).

    The schedule is a plan. Rows are created and replaced only by
    ``buz.asset.action_compute_schedule``; ACLs give no direct write access.
    Posting and reversal go through ``action_post_depreciation`` /
    ``action_reverse``; both validate the group and state server-side.
    """
    _name = 'buz.asset.depreciation.line'
    _description = 'รายการค่าเสื่อมราคาทรัพย์สิน'
    _order = 'asset_id, sequence'

    asset_id = fields.Many2one(
        'buz.asset', required=True, index=True, ondelete='cascade', readonly=True, string='ทรัพย์สิน')
    company_id = fields.Many2one(
        'res.company', related='asset_id.company_id', store=True, index=True, string='บริษัท')
    currency_id = fields.Many2one(
        'res.currency', related='asset_id.currency_id', store=True, string='สกุลเงิน')
    sequence = fields.Integer(required=True, readonly=True, string='ลำดับ')
    name = fields.Char(required=True, readonly=True, string='ชื่อ')
    depreciation_date = fields.Date(required=True, readonly=True, string='วันที่ตัดค่าเสื่อมราคา')
    period_start = fields.Date(required=True, readonly=True, string='เริ่มงวด')
    period_end = fields.Date(required=True, readonly=True, string='สิ้นสุดงวด')
    planned_amount = fields.Monetary(
        currency_field='currency_id', required=True, readonly=True, string='จำนวนที่วางแผนไว้')
    remaining_after = fields.Monetary(
        currency_field='currency_id', readonly=True,
        help="มูลค่าที่ต้องคิดค่าเสื่อมคงเหลือตามแผนหลังงวดนี้", string='คงเหลือหลังงวดนี้')
    state = fields.Selection([
        ('planned', 'วางแผนไว้'),
        ('draft_move', 'ร่างรายการบัญชี'),
        ('posted', 'ลงบัญชีแล้ว'),
        ('reversed', 'กลับรายการแล้ว'),
        ('cancelled', 'ยกเลิกแล้ว'),
        ('exception', 'ข้อยกเว้น'),
    ], required=True, default='planned', readonly=True, string='สถานะ')
    move_id = fields.Many2one('account.move', readonly=True, copy=False, ondelete='restrict', string='รายการบัญชี')
    reversal_move_id = fields.Many2one(
        'account.move', readonly=True, copy=False, ondelete='restrict', string='รายการบัญชีกลับรายการ')
    posted_date = fields.Datetime(readonly=True, copy=False, string='ลงบัญชีเมื่อ')
    idempotency_key = fields.Char(required=True, readonly=True, copy=False, index=True, string='คีย์ป้องกันรายการซ้ำ')
    calculation_version = fields.Integer(readonly=True, string='เวอร์ชันการคำนวณ')
    calculation_snapshot = fields.Text(readonly=True, string='ข้อมูลที่ใช้คำนวณ')
    exception_message = fields.Text(readonly=True, string='ข้อความข้อยกเว้น')

    _sql_constraints = [
        ('idempotency_key_uniq', 'unique(idempotency_key)',
         'คีย์รายการค่าเสื่อมราคาต้องไม่ซ้ำกัน'),
        ('asset_sequence_uniq', 'unique(asset_id, sequence)',
         'แต่ละงวดปรากฏได้เพียงครั้งเดียวต่อทรัพย์สิน'),
        ('planned_amount_non_negative', 'CHECK(planned_amount >= 0)',
         'ค่าเสื่อมราคาตามแผนต้องไม่ติดลบ'),
    ]

    # ------------------------------------------------------------------
    # Posting / reversal
    # ------------------------------------------------------------------
    def _require_accounting_manager(self):
        if not self.env.user.has_group('buz_asset_management.group_asset_accounting_manager'):
            raise AccessError(_("คุณไม่มีสิทธิ์ลงบัญชีหรือกลับรายการค่าเสื่อมราคา"))

    def _lock_rows(self):
        """Serialize concurrent post attempts on the same lines (read-only lock)."""
        self.env.cr.execute(
            'SELECT id FROM buz_asset_depreciation_line WHERE id IN %s FOR UPDATE NOWAIT',
            (tuple(self.ids),))
        self.invalidate_recordset()

    def _check_postable(self):
        """Pre-checks that raise without changing state (user-correctable setup)."""
        self.ensure_one()
        asset = self.asset_id
        category = asset.category_id
        if (asset.approval_state != 'approved' or asset.operational_state not in ('in_service', 'under_maintenance')
                or asset.accounting_state != 'capitalized'):
            raise UserError(_(
                "ทรัพย์สิน %s ต้องอนุมัติ เริ่มใช้งาน และบันทึกเป็นสินทรัพย์แล้ว จึงจะลงบัญชีค่าเสื่อมราคาได้",
                asset.display_name))
        missing = [label for label, value in (
            (_('บัญชีค่าใช้จ่ายค่าเสื่อมราคา'), category.expense_account_id),
            (_('บัญชีค่าเสื่อมราคาสะสม'), category.depreciation_account_id),
            (_('สมุดรายวันค่าเสื่อมราคา'), category.journal_id)) if not value]
        if missing:
            raise UserError(_("หมวดหมู่ %(cat)s ยังไม่ได้ตั้งค่า: %(missing)s",
                              cat=category.display_name, missing=', '.join(missing)))
        for record in (category.expense_account_id, category.depreciation_account_id, category.journal_id):
            if record.company_id != asset.company_id:
                raise UserError(_("%s เป็นของบริษัทอื่น", record.display_name))
        if self.depreciation_date > fields.Date.context_today(self):
            raise UserError(_("งวด %s ยังไม่ถึงกำหนด ลงบัญชีล่วงหน้าไม่ได้", self.name))
        earlier = self.search([
            ('asset_id', '=', asset.id), ('sequence', '<', self.sequence),
            ('state', 'in', ('planned', 'draft_move', 'exception'))], limit=1)
        if earlier:
            raise UserError(_("ต้องลงบัญชีงวด %s ก่อน", earlier.name))

    def _prepare_move_vals(self):
        self.ensure_one()
        asset, category = self.asset_id, self.asset_id.category_id
        base = {'name': self.name, 'currency_id': asset.currency_id.id}
        return {
            'move_type': 'entry',
            'company_id': asset.company_id.id,
            'journal_id': category.journal_id.id,
            'date': self.depreciation_date,
            'ref': '%s - %s' % (asset.code, self.name),
            'buz_asset_line_id': self.id,
            'line_ids': [
                fields.Command.create(dict(base, account_id=category.expense_account_id.id,
                                           debit=self.planned_amount, credit=0.0)),
                fields.Command.create(dict(base, account_id=category.depreciation_account_id.id,
                                           debit=0.0, credit=self.planned_amount)),
            ],
        }

    def action_post_depreciation(self):
        """Post planned lines. Returns the lines left in exception (blocked by policy)."""
        self._require_accounting_manager()
        self._post_lines()

    def _post_lines(self):
        blocked = self.browse()
        for line in self.sorted(lambda l: (l.asset_id.id, l.sequence)):
            line._lock_rows()
            if line.move_id:
                continue  # idempotent: already posted by another call
            if line.state not in ('planned', 'exception'):
                raise UserError(_("งวด %s อยู่ในสถานะที่ลงบัญชีไม่ได้", line.name))
            if float_is_zero(line.planned_amount, precision_rounding=line.currency_id.rounding):
                raise UserError(_("งวด %s มีจำนวนเงินเป็นศูนย์", line.name))
            line._check_postable()
            try:
                with self.env.cr.savepoint():
                    # No sudo / no override context: Odoo lock dates and the
                    # Accounting Date Policy validate this create/post as usual.
                    move = self.env['account.move'].create(line._prepare_move_vals())
                    move.action_post()
                    # Odoo's _post() silently moves a locked-period date to the next
                    # open period. A depreciation period must keep its own date, so
                    # treat a shifted date as blocked and roll the move back.
                    if move.date != line.depreciation_date:
                        raise UserError(_(
                            "วันที่ %(planned)s อยู่ในงวดที่ถูกล็อก ระบบบัญชีจะเลื่อนเป็น %(actual)s จึงไม่ลงบัญชีให้",
                            planned=line.depreciation_date, actual=move.date))
            except UserError as exc:
                line.sudo().write({'state': 'exception', 'exception_message': exc.args[0]})
                blocked |= line
                continue
            line.sudo().write({
                'move_id': move.id, 'state': 'posted', 'exception_message': False,
                'posted_date': fields.Datetime.now()})
        return blocked

    def action_reverse(self, reason=None, reversal_date=None):
        self._require_accounting_manager()
        for line in self:
            line._lock_rows()
            if line.state == "reversed" and line.reversal_move_id:
                continue
            if line.state != "posted" or not line.move_id:
                raise UserError(_("งวด %s ยังไม่ได้ลงบัญชี จึงกลับรายการไม่ได้", line.name))
            if line.reversal_move_id:
                continue
            date = reversal_date or fields.Date.context_today(self)
            # Policy/lock errors propagate: nothing is changed on failure.
            reversal = line.move_id._reverse_moves([{
                'ref': _("กลับรายการ %(ref)s: %(reason)s", ref=line.move_id.name, reason=reason or '-'),
                'date': date}], cancel=True)
            line.sudo().write({'state': 'reversed', 'reversal_move_id': reversal.id})
            line.asset_id.sudo().message_post(
                author_id=self.env.user.partner_id.id,
                body=_("กลับรายการค่าเสื่อมราคา %(name)s: %(reason)s", name=line.name, reason=reason or '-'))

    def _cron_post_due_lines(self, batch_size=100):
        """Post due lines for companies that enabled auto-post; safe to rerun."""
        today = fields.Date.context_today(self)
        companies = self.env['res.company'].search([('buz_asset_auto_post', '=', True)])
        lines = self.search([
            ('state', '=', 'planned'), ('depreciation_date', '<=', today),
            ('company_id', 'in', companies.ids)], order='asset_id, sequence', limit=batch_size)
        for line in lines:
            try:
                with self.env.cr.savepoint():
                    line._post_lines()
            except Exception:  # per-line isolation; logged and left for next run
                _logger.exception('Asset depreciation auto-post failed for line %s', line.id)
