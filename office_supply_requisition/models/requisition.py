# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class OfficeSupplyRequisition(models.Model):
    _name = 'office.supply.requisition'
    _inherit = ['mail.thread']
    _description = 'ใบเบิกของสำนักงาน'
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(string='เลขที่ใบเบิก', default='New', readonly=True, copy=False)
    employee_id = fields.Many2one(
        'hr.employee', string='ผู้เบิก', required=True,
        default=lambda self: self.env.user.employee_id.id)
    requester_id = fields.Many2one(
        'hr.employee', string='ผู้ขอเบิก', required=True,
        default=lambda self: self.env.user.employee_id.id)
    receiver_id = fields.Many2one(
        'hr.employee', string='ผู้รับอุปกรณ์', required=True,
        default=lambda self: self.env.user.employee_id.id)
    date = fields.Datetime(string='วันที่เบิก', default=fields.Datetime.now, required=True)
    location_id = fields.Many2one(
        'stock.location', string='คลังที่เบิกออก', required=True,
        domain=[('usage', '=', 'internal')],
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        ).lot_stock_id)
    line_ids = fields.One2many(
        'office.supply.requisition.line', 'requisition_id', string='รายการเบิก')
    state = fields.Selection(
        [('draft', 'ร่าง'), ('confirmed', 'ยืนยันการเบิก'), ('signed', 'เซ็นรับแล้ว'), ('done', 'เบิกแล้ว')],
        default='draft', string='สถานะ', tracking=True, copy=False)
    submitted_by_id = fields.Many2one('res.users', string='ส่งโดย', readonly=True, copy=False)
    submitted_date = fields.Datetime(string='วันที่ส่ง', readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='อนุมัติโดย', readonly=True, copy=False)
    approved_date = fields.Datetime(string='วันที่อนุมัติ', readonly=True, copy=False)
    signed_by = fields.Char(string='ผู้เซ็นรับ', readonly=True, copy=False)
    signed_on = fields.Datetime(string='วันที่เซ็นรับ', readonly=True, copy=False)
    signature = fields.Binary(string='ลายเซ็นผู้รับ', attachment=True, copy=False)
    reject_reason = fields.Text(string='เหตุผลที่ปฏิเสธ', copy=False)
    note = fields.Text(string='หมายเหตุ')
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, required=True)
    amount_total = fields.Monetary(
        string='มูลค่ารวม', compute='_compute_amount_total', store=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id, required=True)

    @api.depends('line_ids.price_subtotal')
    def _compute_amount_total(self):
        for req in self:
            req.amount_total = sum(req.line_ids.mapped('price_subtotal'))

    def _can_approve(self):
        return self.env.user.has_group('office_supply_requisition.group_office_supply_manager')

    def write(self, vals):
        if any(record.state == 'done' for record in self):
            allowed_done_write_fields = {
                'note',
                'state',
                'approved_by_id',
                'approved_date',
                'submitted_by_id',
                'submitted_date',
                'signed_by',
                'signed_on',
                'signature',
                'reject_reason',
            }
            disallowed = set(vals) - allowed_done_write_fields
            if disallowed:
                raise UserError('ไม่สามารถแก้ไขใบเบิกที่มีสถานะเบิกแล้วได้')
        return super().write(vals)

    def unlink(self):
        if any(record.state == 'done' for record in self):
            raise UserError('ไม่สามารถลบใบเบิกที่มีสถานะเบิกแล้วได้')
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'office.supply.requisition') or 'New'
        return super().create(vals_list)

    def action_submit(self):
        for req in self:
            if req.state != 'draft':
                continue
            if not req.line_ids:
                raise UserError('กรุณาเพิ่มรายการที่ต้องการเบิกก่อน')
            req.write({
                'state': 'confirmed',
                'submitted_by_id': self.env.user.id,
                'submitted_date': fields.Datetime.now(),
                'reject_reason': False,
            })
            req.message_post(body='ยืนยันการเบิกแล้ว รอการเซ็นรับจากผู้รับอุปกรณ์')
        return True

    def action_confirm_request(self):
        return self.action_submit()

    def action_approve(self):
        for req in self:
            if req.state == 'done':
                continue
            if req.state not in ('confirmed', 'signed'):
                raise UserError('ใบเบิกต้องอยู่ในสถานะยืนยันการเบิกก่อนจึงจะอนุมัติได้')
            if not req._can_approve():
                raise UserError('เฉพาะผู้จัดการเท่านั้นที่สามารถอนุมัติใบเบิกได้')
            req.write({
                'state': 'signed',
                'approved_by_id': self.env.user.id,
                'approved_date': fields.Datetime.now(),
                'reject_reason': False,
            })
            req.message_post(body='ใบเบิกได้รับการยืนยันและพร้อมสำหรับการเซ็นรับ')
        return True

    def action_reject(self):
        for req in self:
            if req.state not in ('confirmed', 'signed'):
                raise UserError('เฉพาะใบเบิกที่ยืนยันการเบิกแล้วเท่านั้นที่สามารถปฏิเสธได้')
            if not req._can_approve():
                raise UserError('เฉพาะผู้จัดการเท่านั้นที่สามารถปฏิเสธใบเบิกได้')
            req.write({
                'state': 'draft',
                'approved_by_id': False,
                'approved_date': False,
                'reject_reason': req.reject_reason or 'ใบเบิกถูกปฏิเสธโดยผู้อนุมัติ',
            })
            req.message_post(body='ใบเบิกถูกปฏิเสธ: %s' % (req.reject_reason or 'ไม่ระบุเหตุผล'))
        return True

    def action_confirm(self):
        """เซ็นรับและยืนยันการเบิก: สร้าง Stock Move หลังจากเซ็นรับแล้ว"""
        for req in self:
            if req.state == 'done':
                continue
            if req.state == 'draft':
                raise UserError('กรุณายืนยันการเบิกก่อน')
            if not req.receiver_id:
                raise UserError('กรุณาเลือกผู้รับอุปกรณ์ก่อน')
            if not req.signature:
                raise UserError('กรุณาเซ็นรับบนมือถือหรือแท็บเล็ตก่อนยืนยัน')
            if not req.line_ids:
                raise UserError('กรุณาเพิ่มรายการที่ต้องการเบิกก่อน')
            for line in req.line_ids:
                line._validate_for_confirm()
            for line in req.line_ids:
                line._deduct_stock()
            req.write({
                'state': 'done',
                'signed_by': req.receiver_id.name or self.env.user.name,
                'signed_on': fields.Datetime.now(),
            })
            req.message_post(body='ใบเบิกได้รับการเซ็นรับและยืนยันแล้ว และมีการตัดสต๊อกเรียบร้อย')
        return True

    def action_sign_and_confirm(self):
        return self.action_confirm()

    def action_reset_draft(self):
        for req in self:
            if req.state != 'done':
                continue
            for line in req.line_ids:
                if line.stock_move_id:
                    line._reverse_stock()
                    line.stock_move_id = False
            req.write({
                'state': 'draft',
                'approved_by_id': False,
                'approved_date': False,
                'submitted_by_id': False,
                'submitted_date': False,
                'signed_by': False,
                'signed_on': False,
                'signature': False,
                'reject_reason': False,
            })
            req.message_post(body='ใบเบิกถูกตั้งกลับเป็นร่างและคืนสต๊อกแล้ว')
        return True


class OfficeSupplyRequisitionLine(models.Model):
    _name = 'office.supply.requisition.line'
    _description = 'รายการเบิกของสำนักงาน'

    requisition_id = fields.Many2one(
        'office.supply.requisition', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', string='สินค้า', required=True,
        domain=[('type', '=', 'product')])
    product_uom_qty = fields.Float(string='จำนวนที่เบิก', default=1.0, required=True)
    product_uom_id = fields.Many2one(
        'uom.uom', string='หน่วยนับ', related='product_id.uom_id', readonly=True, store=True)
    qty_available = fields.Float(
        string='คงเหลือในคลัง', related='product_id.qty_available', readonly=True)
    state = fields.Selection(related='requisition_id.state', store=True)
    date = fields.Datetime(related='requisition_id.date', store=True, string='วันที่เบิก')
    employee_id = fields.Many2one(
        related='requisition_id.employee_id', store=True, string='ผู้เบิก')
    price_unit = fields.Float(
        string='ราคาต้นทุน/หน่วย', related='product_id.standard_price', readonly=True)
    price_subtotal = fields.Monetary(
        string='มูลค่า', compute='_compute_price_subtotal', store=True,
        currency_field='currency_id')
    currency_id = fields.Many2one(related='requisition_id.currency_id', store=True)
    stock_move_id = fields.Many2one(
        'stock.move', string='Stock Move', readonly=True, copy=False)

    @api.constrains('product_uom_qty')
    def _check_product_uom_qty(self):
        for line in self:
            if line.product_uom_qty <= 0:
                raise UserError('จำนวนที่เบิกต้องมากกว่า 0')

    @api.constrains('requisition_id', 'product_id')
    def _check_duplicate_product(self):
        for line in self:
            if not line.product_id or not line.requisition_id:
                continue
            existing = self.search([
                ('requisition_id', '=', line.requisition_id.id),
                ('product_id', '=', line.product_id.id),
                ('id', '!=', line.id),
            ], limit=1)
            if existing:
                raise UserError('สินค้านี้ถูกเพิ่มในใบเบิกแล้ว')

    @api.depends('product_uom_qty', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.product_uom_qty * line.price_unit

    def _get_consume_location(self):
        """location ปลายทางสำหรับของที่ถูกเบิกออกไปใช้ (virtual/consumption location)"""
        location = self.env.ref('stock.stock_location_scrap', raise_if_not_found=False)
        if not location:
            location = self.env['stock.location'].search(
                [('usage', '=', 'inventory')], limit=1)
        return location

    def _validate_for_confirm(self):
        self.ensure_one()
        if not self.product_id:
            raise UserError('กรุณาเลือกสินค้าให้ครบถ้วนก่อนเบิก')
        if self.product_uom_qty <= 0:
            raise UserError('จำนวนที่เบิกต้องมากกว่า 0')
        if not self.requisition_id.location_id or self.requisition_id.location_id.usage != 'internal':
            raise UserError('คลังที่เบิกออกต้องเป็นคลัง internal เท่านั้น')
        available_qty = self.product_id.with_context(location=self.requisition_id.location_id.id).qty_available
        if available_qty < self.product_uom_qty:
            raise UserError(
                'สินค้า %s มีปริมาณไม่เพียงพอในคลัง %s (คงเหลือ %s, ต้องการ %s)' % (
                    self.product_id.display_name,
                    self.requisition_id.location_id.display_name,
                    available_qty,
                    self.product_uom_qty,
                )
            )

    def _deduct_stock(self):
        self.ensure_one()
        req = self.requisition_id
        self._validate_for_confirm()
        dest_location = self._get_consume_location()
        if not dest_location:
            raise UserError('ไม่พบ location ปลายทางสำหรับตัดสต๊อก กรุณาตั้งค่าใน Inventory ก่อน')
        if self.stock_move_id:
            return self.stock_move_id

        move_vals = {
            'name': req.name or 'เบิกของสำนักงาน',
            'product_id': self.product_id.id,
            'product_uom_qty': self.product_uom_qty,
            'product_uom': self.product_uom_id.id,
            'location_id': req.location_id.id,
            'location_dest_id': dest_location.id,
            'origin': req.name,
            'company_id': req.company_id.id,
        }
        move = self.env['stock.move'].create(move_vals)
        self.stock_move_id = move.id
        move._action_confirm()
        move._action_assign()
        for move_line in move.move_line_ids:
            if 'quantity' in move_line._fields:
                move_line.quantity = self.product_uom_qty
            elif 'qty_done' in move_line._fields:
                move_line.qty_done = self.product_uom_qty
        move._action_done()
        return move

    def _reverse_stock(self):
        self.ensure_one()
        if not self.stock_move_id:
            return False
        req = self.requisition_id
        source_location = self.stock_move_id.location_dest_id or self._get_consume_location()
        if not source_location:
            raise UserError('ไม่พบ location ที่ใช้สำหรับคืนสต๊อกกลับ')

        reverse_vals = {
            'name': req.name or 'คืนสต๊อกเบิกของสำนักงาน',
            'product_id': self.product_id.id,
            'product_uom_qty': self.product_uom_qty,
            'product_uom': self.product_uom_id.id,
            'location_id': source_location.id,
            'location_dest_id': req.location_id.id,
            'origin': req.name,
            'company_id': req.company_id.id,
        }
        reverse_move = self.env['stock.move'].create(reverse_vals)
        reverse_move._action_confirm()
        reverse_move._action_assign()
        for move_line in reverse_move.move_line_ids:
            if 'quantity' in move_line._fields:
                move_line.quantity = self.product_uom_qty
            elif 'qty_done' in move_line._fields:
                move_line.qty_done = self.product_uom_qty
        reverse_move._action_done()
        return reverse_move
