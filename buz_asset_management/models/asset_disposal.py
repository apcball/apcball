# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

STATE_GUARDED = ('state',)


class BuzAssetDisposal(models.Model):
    """Disposal / sale / write-off of one asset.

    The disposal entry removes cost and accumulated depreciation. Proceeds are
    never booked here: when a customer invoice is linked, its revenue line must
    sit on the category's disposal clearing account and this entry settles that
    account into gain/loss, so proceeds are counted once.
    """
    _name = 'buz.asset.disposal'
    _description = 'การจำหน่ายทรัพย์สิน'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'disposal_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(readonly=True, copy=False, default='/', string='เลขที่')
    asset_id = fields.Many2one(
        'buz.asset', required=True, index=True, tracking=True, check_company=True,
        ondelete='restrict', string='ทรัพย์สิน')
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company, string='บริษัท')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True, string='สกุลเงิน')
    disposal_type = fields.Selection([
        ('sale', 'ขาย'),
        ('scrap', 'ตัดจำหน่าย/ทิ้ง'),
        ('lost', 'สูญหาย'),
    ], required=True, default='scrap', tracking=True, string='ประเภทการจำหน่าย')
    disposal_date = fields.Date(
        required=True, default=fields.Date.context_today, tracking=True, string='วันที่จำหน่าย')
    reason = fields.Text(required=True, string='เหตุผล')
    sale_move_id = fields.Many2one(
        'account.move', check_company=True, copy=False, tracking=True,
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]",
        string='ใบแจ้งหนี้ขาย')
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('approved', 'อนุมัติแล้ว'),
        ('posted', 'ลงบัญชีแล้ว'),
        ('cancelled', 'ยกเลิก'),
    ], required=True, default='draft', copy=False, tracking=True, string='สถานะ')

    cost = fields.Monetary(currency_field='currency_id', readonly=True, copy=False, string='ราคาทุน')
    accumulated_depreciation = fields.Monetary(
        currency_field='currency_id', readonly=True, copy=False, string='ค่าเสื่อมราคาสะสม')
    carrying_value = fields.Monetary(currency_field='currency_id', readonly=True, copy=False, string='มูลค่าตามบัญชี')
    proceeds = fields.Monetary(
        currency_field='currency_id', readonly=True, copy=False,
        help="รายได้จากใบแจ้งหนี้ขายที่ลงในบัญชีพักการจำหน่าย", string='ผลตอบแทนจากการขาย')
    gain_loss = fields.Monetary(
        currency_field='currency_id', readonly=True, copy=False,
        help="บวกคือกำไร ลบคือขาดทุน", string='กำไร/(ขาดทุน)')
    move_id = fields.Many2one('account.move', readonly=True, copy=False, ondelete='restrict', string='รายการบัญชี')

    # ------------------------------------------------------------------
    def _check_state_write(self, vals):
        if not self.env.su and any(field in vals for field in STATE_GUARDED + (
                'cost', 'accumulated_depreciation', 'carrying_value', 'proceeds', 'gain_loss', 'move_id')):
            raise AccessError(_("ฟิลด์สถานะและตัวเลขบัญชีเปลี่ยนได้ผ่านขั้นตอนการทำงาน (workflow) เท่านั้น"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_state_write({k: v for k, v in vals.items() if k != 'state' or v != 'draft'})
            company = (self.env['res.company'].browse(vals['company_id'])
                       if vals.get('company_id') else self.env.company)
            vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('buz.asset.disposal') or '/'
        return super().create(vals_list)

    def write(self, vals):
        self._check_state_write(vals)
        if not self.env.su and any(d.state != 'draft' for d in self):
            raise UserError(_("แก้ไขได้เฉพาะการจำหน่ายที่เป็นร่าง"))
        return super().write(vals)

    def unlink(self):
        if any(d.state not in ('draft', 'cancelled') for d in self):
            raise UserError(_("ลบได้เฉพาะการจำหน่ายที่เป็นร่างหรือยกเลิกแล้ว"))
        return super().unlink()

    @api.constrains('asset_id', 'state')
    def _check_one_open_disposal(self):
        for disposal in self.filtered(lambda d: d.state != 'cancelled'):
            if self.search_count([('asset_id', '=', disposal.asset_id.id), ('state', '!=', 'cancelled'),
                                  ('id', '!=', disposal.id)]):
                raise ValidationError(_("ทรัพย์สิน %s มีรายการจำหน่ายอยู่แล้ว", disposal.asset_id.display_name))

    @api.constrains('sale_move_id', 'disposal_type')
    def _check_sale_link(self):
        for disposal in self.filtered('sale_move_id'):
            if disposal.disposal_type != 'sale':
                raise ValidationError(_("ผูกใบแจ้งหนี้ขายได้เฉพาะการจำหน่ายประเภทขาย"))

    # ------------------------------------------------------------------
    def _require_group(self, xmlid):
        if not self.env.user.has_group(xmlid):
            raise AccessError(_("คุณไม่มีสิทธิ์ทำรายการนี้"))

    def action_approve(self):
        self._require_group('buz_asset_management.group_asset_manager')
        for disposal in self:
            if disposal.state != 'draft':
                raise UserError(_("อนุมัติได้เฉพาะการจำหน่ายที่เป็นร่าง"))
            disposal._check_asset_ready()
        self.sudo().write({'state': 'approved'})  # sudo: state guard; group checked above

    def action_cancel(self):
        self._require_group('buz_asset_management.group_asset_manager')
        if any(d.state not in ('draft', 'approved') for d in self):
            raise UserError(_("ยกเลิกได้เฉพาะการจำหน่ายที่เป็นร่างหรืออนุมัติแล้ว"))
        self.sudo().write({'state': 'cancelled'})  # sudo: state guard; group checked above

    def _check_asset_ready(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.operational_state == 'disposed' or asset.accounting_state != 'capitalized':
            raise UserError(_("ทรัพย์สิน %s ต้องบันทึกเป็นสินทรัพย์แล้วและยังไม่ถูกจำหน่าย", asset.display_name))
        if asset.approval_state != 'approved':
            raise UserError(_("ทรัพย์สิน %s ยังไม่อนุมัติ", asset.display_name))

    def _compute_figures(self):
        """Carrying value from POSTED depreciation lines only; blocks on gaps."""
        self.ensure_one()
        asset, rounding = self.asset_id, self.currency_id.rounding
        lines = asset.depreciation_line_ids
        due = lines.filtered(lambda l: l.depreciation_date <= self.disposal_date)
        not_posted = due.filtered(lambda l: l.state != 'posted')
        if not_posted:
            raise UserError(_(
                "ต้องลงบัญชีค่าเสื่อมราคาถึงวันที่จำหน่ายให้ครบก่อน (ค้าง: %s)",
                ', '.join(not_posted.mapped('name'))))
        accumulated = sum(due.mapped('planned_amount'))
        cost = asset.gross_cost
        carrying = cost - accumulated
        proceeds = 0.0
        category = asset.category_id
        if self.sale_move_id:
            sale = self.sale_move_id
            if sale.company_id != self.company_id or sale.state != 'posted' or sale.move_type != 'out_invoice':
                raise UserError(_("ใบแจ้งหนี้ขายต้องเป็นของบริษัทเดียวกันและลงบัญชีแล้ว"))
            if not category.disposal_clearing_account_id:
                raise UserError(_("หมวดหมู่ %s ยังไม่ได้ตั้งบัญชีพักการจำหน่าย", category.display_name))
            clearing = sale.line_ids.filtered(lambda l: l.account_id == category.disposal_clearing_account_id)
            if not clearing:
                raise UserError(_("ใบแจ้งหนี้ขายไม่มีรายการในบัญชีพักการจำหน่าย จึงจะนับรายได้ซ้ำไม่ได้"))
            proceeds = sum(clearing.mapped('credit')) - sum(clearing.mapped('debit'))
            if float_compare(proceeds, 0.0, precision_rounding=rounding) < 0:
                raise UserError(_("รายได้จากการขายในบัญชีพักการจำหน่ายต้องไม่ติดลบ"))
        return cost, accumulated, carrying, proceeds

    def _prepare_move_vals(self, cost, accumulated, proceeds, gain_loss):
        self.ensure_one()
        category, rounding = self.asset_id.category_id, self.currency_id.rounding
        missing = [label for label, value in (
            (_('บัญชีสินทรัพย์ถาวร'), category.asset_account_id),
            (_('บัญชีค่าเสื่อมราคาสะสม'), category.depreciation_account_id),
            (_('บัญชีกำไร/ขาดทุนจากการจำหน่าย'), category.gain_loss_account_id),
            (_('สมุดรายวัน'), category.journal_id)) if not value]
        if missing:
            raise UserError(_("หมวดหมู่ %(cat)s ยังไม่ได้ตั้งค่า: %(missing)s",
                              cat=category.display_name, missing=', '.join(missing)))
        label = '%s - %s' % (self.name, self.asset_id.code)

        def line(account, debit=0.0, credit=0.0):
            return Command.create({'name': label, 'account_id': account.id, 'debit': debit, 'credit': credit})

        lines = [line(category.asset_account_id, credit=cost)]
        if not float_is_zero(accumulated, precision_rounding=rounding):
            lines.append(line(category.depreciation_account_id, debit=accumulated))
        if not float_is_zero(proceeds, precision_rounding=rounding):
            lines.append(line(category.disposal_clearing_account_id, debit=proceeds))
        if not float_is_zero(gain_loss, precision_rounding=rounding):
            if gain_loss < 0:
                lines.append(line(category.gain_loss_account_id, debit=-gain_loss))
            else:
                lines.append(line(category.gain_loss_account_id, credit=gain_loss))
        return {
            'move_type': 'entry', 'company_id': self.company_id.id, 'journal_id': category.journal_id.id,
            'date': self.disposal_date, 'ref': label, 'buz_disposal_id': self.id, 'line_ids': lines}

    def action_post(self):
        self._require_group('buz_asset_management.group_asset_accounting_manager')
        for disposal in self:
            if disposal.move_id:
                continue  # idempotent
            if disposal.state != 'approved':
                raise UserError(_("ลงบัญชีได้เฉพาะการจำหน่ายที่อนุมัติแล้ว"))
            disposal._check_asset_ready()
            rounding = disposal.currency_id.rounding
            cost, accumulated, carrying, proceeds = disposal._compute_figures()
            gain_loss = proceeds - carrying  # >0 gain
            vals = disposal._prepare_move_vals(cost, accumulated, proceeds, gain_loss)
            # No sudo / override: lock dates and the Accounting Date Policy apply as usual.
            # Errors propagate: the disposal stays approved and nothing is written.
            with self.env.cr.savepoint():
                move = self.env['account.move'].create(vals)
                move.action_post()
                if move.date != disposal.disposal_date:
                    raise UserError(_(
                        "วันที่ %(planned)s อยู่ในงวดที่ถูกล็อก ระบบบัญชีจะเลื่อนเป็น %(actual)s จึงไม่ลงบัญชีให้",
                        planned=disposal.disposal_date, actual=move.date))
            asset = disposal.asset_id
            # sudo: state/line writes are workflow-guarded; group checked above.
            future = asset.depreciation_line_ids.filtered(
                lambda l: l.depreciation_date > disposal.disposal_date and l.state in ('planned', 'exception'))
            future.sudo().write({'state': 'cancelled'})
            asset.sudo().write({'operational_state': 'disposed', 'accounting_state': 'disposed'})
            disposal.sudo().write({
                'state': 'posted', 'move_id': move.id, 'cost': cost, 'accumulated_depreciation': accumulated,
                'carrying_value': carrying, 'proceeds': proceeds, 'gain_loss': gain_loss})
            asset.sudo().message_post(
                author_id=self.env.user.partner_id.id,
                body=_("จำหน่ายทรัพย์สิน %(name)s: มูลค่าตามบัญชี %(cv)s กำไร/(ขาดทุน) %(gl)s",
                       name=disposal.name, cv=carrying, gl=gain_loss))
