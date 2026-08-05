from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BuzItConsumableRequestLine(models.Model):
    _name = 'buz.it.consumable.request.line'
    _description = 'IT Consumable Request Line'
    _order = 'id'

    request_id = fields.Many2one(
        'buz.it.consumable.request',
        string='คำขอ',
        required=True,
        ondelete='cascade',
        index=True,
    )
    consumable_id = fields.Many2one(
        'buz.it.consumable',
        string='สินค้า',
        required=True,
        ondelete='restrict',
        index=True,
    )
    unit = fields.Char(
        related='consumable_id.unit',
        string='หน่วย',
        store=True,
        readonly=True,
    )
    requested_qty = fields.Float(
        string='จำนวนที่ขอ',
        digits=(16, 0),
        required=True,
        default=0.0,
    )
    delivered_qty = fields.Float(
        string='จำนวนที่จ่าย',
        digits=(16, 0),
        default=0.0,
        readonly=True,
        copy=False,
    )
    remaining_qty = fields.Float(
        compute='_compute_remaining_qty',
        string='เหลือจ่าย',
        digits=(16, 0),
        store=True,
    )
    location_id = fields.Many2one(
        'buz.it.stock.location',
        string='Location ที่จ่าย',
        readonly=True,
        copy=False,
    )
    state = fields.Selection([
        ('pending', 'ยังไม่จ่าย'),
        ('partial', 'จ่ายบางส่วน'),
        ('done', 'เสร็จสิ้น'),
        ('rejected', 'ปฏิเสธ'),
    ], compute='_compute_state', store=True, string='สถานะ', copy=False)
    rejected = fields.Boolean(string='ปฏิเสธ', default=False, copy=False)
    reason = fields.Text(string='เหตุผล', copy=False)
    history_ids = fields.One2many(
        'buz.it.stock.history',
        'request_line_id',
        string='ประวัติการจ่าย',
        readonly=True,
    )

    @api.depends('requested_qty', 'delivered_qty')
    def _compute_remaining_qty(self):
        for rec in self:
            rec.remaining_qty = rec.requested_qty - rec.delivered_qty

    @api.depends('requested_qty', 'delivered_qty', 'rejected')
    def _compute_state(self):
        for rec in self:
            if rec.rejected:
                rec.state = 'rejected'
            elif rec.requested_qty > 0 and rec.delivered_qty >= rec.requested_qty:
                rec.state = 'done'
            elif rec.delivered_qty > 0:
                rec.state = 'partial'
            else:
                rec.state = 'pending'

    def _get_deliverable_locations(self):
        self.ensure_one()
        return self.consumable_id.quant_ids.filtered(
            lambda q: q.qty > 0
        ).location_id

    def _do_deliver(self, qty, location):
        self.ensure_one()
        if not self.env.user.has_group('buz_it_helpdesk.group_it_support_agent'):
            raise UserError(_('เฉพาะ Support Agent เท่านั้นที่จ่ายของได้'))
        if self.rejected:
            raise UserError(_('รายการนี้ถูกปฏิเสธแล้ว'))
        if self.request_id.state not in ('confirmed', 'partial'):
            raise UserError(_('คำขออยู่ในสถานะที่ไม่สามารถจ่ายของได้'))
        if qty <= 0:
            raise UserError(_('จำนวนที่จ่ายต้องมากกว่า 0'))
        if qty > self.remaining_qty:
            raise UserError(_('จำนวนที่จ่ายเกินยอดที่ขอยังเหลือ (%s %s)') % (
                self.remaining_qty, self.unit,
            ))
        if location.company_id != self.consumable_id.company_id:
            raise UserError(_('Location และสินค้าต้องอยู่บริษัทเดียวกัน'))
        quant = self.env['buz.it.stock.quant'].search([
            ('consumable_id', '=', self.consumable_id.id),
            ('location_id', '=', location.id),
        ], limit=1)
        if not quant or quant.qty < qty:
            available = quant.qty if quant else 0.0
            raise UserError(_('ของไม่พอจ่ายจาก %s (เหลือ %s %s)') % (
                location.name, available, self.unit,
            ))
        self.env.cr.flush()
        self.env.cr.execute(
            'SELECT id FROM buz_it_stock_quant WHERE id = %s FOR UPDATE',
            (quant.id,),
        )
        quant = quant.sudo()
        quant.invalidate_recordset(['qty'])
        quant.qty -= qty
        self.with_context(buz_consumable_transition=True).write({
            'delivered_qty': self.delivered_qty + qty,
            'location_id': location.id,
            'rejected': False,
            'reason': False,
        })
        self.env['buz.it.stock.history'].sudo().create({
            'move_type': 'out',
            'consumable_id': self.consumable_id.id,
            'location_id': location.id,
            'qty': -qty,
            'move_date': fields.Date.context_today(self),
            'reference': self.request_id.name,
            'request_line_id': self.id,
            'note': _('จ่ายตามคำขอ %s') % self.request_id.name,
        })
        self.request_id.with_context(buz_consumable_transition=True).write({
            'payer_id': self.env.user.id,
        })
        self.request_id._recompute_state()
        return True

    def action_deliver(self):
        self.ensure_one()
        return {
            'name': _('จ่ายรายการ'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.it.consumable.deliver.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id},
        }

    def action_reject(self):
        self.ensure_one()
        return {
            'name': _('ปฏิเสธรายการ'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.it.consumable.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id},
        }

    def action_deliver_auto(self):
        self.ensure_one()
        available = self.consumable_id.quant_ids.filtered(
            lambda q: q.qty > 0 and q.qty >= self.remaining_qty
        )
        if len(available) != 1:
            raise UserError(_(
                'รายการ %s ต้องเลือก Location หรือของไม่พอ'
            ) % self.consumable_id.display_name)
        return self._do_deliver(self.remaining_qty, available.location_id)

    def write(self, vals):
        if 'requested_qty' in vals:
            for rec in self:
                new_qty = vals.get('requested_qty', rec.requested_qty)
                max_qty = rec.consumable_id.max_per_request
                if max_qty and new_qty > max_qty:
                    raise UserError(_(
                        'จำนวนที่ขอเกินสูงสุดต่อคำขอ (%s %s)'
                    ) % (max_qty, rec.unit))
                if new_qty < rec.delivered_qty:
                    raise UserError(_('จำนวนที่ขอต้องไม่น้อยกว่าจำนวนที่จ่ายแล้ว'))
        if self.env.context.get('buz_consumable_transition'):
            return super().write(vals)
        is_agent = self.env.user.has_group(
            'buz_it_helpdesk.group_it_support_agent'
        )
        for rec in self:
            request = rec.request_id
            if request.state != 'draft':
                if not is_agent:
                    raise UserError(_('ไม่สามารถแก้ไขรายการหลังจากส่งคำขอแล้ว'))
            elif not (request.requester_id == self.env.user or is_agent):
                raise UserError(_('ไม่สามารถแก้ไขรายการของคำขอนี้ได้'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            request = self.env['buz.it.consumable.request'].browse(
                vals.get('request_id')
            )
            if not request or request.state != 'draft':
                raise UserError(_('เพิ่มรายการได้เฉพาะในฉบับร่างเท่านั้น'))
            if not (
                request.requester_id == self.env.user
                or self.env.user.has_group(
                    'buz_it_helpdesk.group_it_support_agent'
                )
            ):
                raise UserError(_('ไม่สามารถเพิ่มรายการในคำขอนี้ได้'))
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            request = rec.request_id
            if request.state != 'draft':
                raise UserError(_('ลบรายการได้เฉพาะในฉบับร่างเท่านั้น'))
            if not (
                request.requester_id == self.env.user
                or self.env.user.has_group(
                    'buz_it_helpdesk.group_it_support_agent'
                )
            ):
                raise UserError(_('ไม่สามารถลบรายการของคำขอนี้ได้'))
        return super().unlink()
