from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BuzItConsumableRequest(models.Model):
    _name = 'buz.it.consumable.request'
    _description = 'IT Consumable Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='เลขที่คำขอ',
        required=True,
        readonly=True,
        copy=False,
        default='New',
    )
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('confirmed', 'รอจ่าย'),
        ('partial', 'จ่ายบางส่วน'),
        ('done', 'เสร็จสิ้น'),
        ('rejected', 'ปฏิเสธ'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='draft', required=True, tracking=True, copy=False)
    requester_id = fields.Many2one(
        'res.users',
        string='ผู้ขอ',
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
        copy=False,
        index=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='พนักงาน',
        copy=False,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='แผนก',
        copy=False,
    )
    company_id = fields.Many2one(
        'res.company',
        string='บริษัท',
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
    )
    request_date = fields.Date(
        string='วันที่ขอ',
        default=fields.Date.context_today,
        required=True,
    )
    reason = fields.Text(string='เหตุผล')
    line_ids = fields.One2many(
        'buz.it.consumable.request.line',
        'request_id',
        string='รายการ',
        copy=False,
    )
    line_count = fields.Integer(
        compute='_compute_line_count',
        string='จำนวนรายการ',
    )
    total_delivered = fields.Float(
        compute='_compute_totals',
        string='จ่ายแล้วทั้งหมด',
        digits=(16, 0),
    )
    payer_id = fields.Many2one(
        'res.users',
        string='ผู้จ่าย',
        readonly=True,
        copy=False,
    )
    pay_date = fields.Date(
        string='วันที่จ่าย',
        readonly=True,
        copy=False,
    )
    show_submit = fields.Boolean(compute='_compute_show_submit')
    show_deliver_all = fields.Boolean(compute='_compute_show_deliver_all')
    show_cancel = fields.Boolean(compute='_compute_show_cancel')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.depends('line_ids.delivered_qty')
    def _compute_totals(self):
        for rec in self:
            rec.total_delivered = sum(rec.line_ids.mapped('delivered_qty'))

    @api.depends('state', 'requester_id')
    @api.depends_context('uid')
    def _compute_show_submit(self):
        is_manager = self._is_manager()
        for rec in self:
            rec.show_submit = (
                rec.state == 'draft'
                and (is_manager or rec.requester_id == self.env.user)
            )

    @api.depends('state', 'line_ids.state')
    @api.depends_context('uid')
    def _compute_show_deliver_all(self):
        is_agent = self._is_agent()
        for rec in self:
            rec.show_deliver_all = (
                is_agent
                and rec.state in ('confirmed', 'partial')
                and any(
                    line.state in ('pending', 'partial')
                    for line in rec.line_ids
                )
            )

    @api.depends('state', 'requester_id')
    @api.depends_context('uid')
    def _compute_show_cancel(self):
        is_agent = self._is_agent()
        for rec in self:
            if rec.state == 'draft':
                rec.show_cancel = is_agent or rec.requester_id == self.env.user
            elif rec.state == 'confirmed':
                rec.show_cancel = is_agent
            else:
                rec.show_cancel = False

    def _is_agent(self):
        return self.env.user.has_group(
            'buz_it_helpdesk.group_it_support_agent'
        )

    def _is_manager(self):
        return self.env.user.has_group(
            'buz_it_helpdesk.group_it_helpdesk_manager'
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['state'] = 'draft'
            requester = self.env['res.users'].browse(
                vals.get('requester_id') or self.env.uid
            )
            if requester.exists() and requester.employee_id:
                vals['employee_id'] = (
                    vals.get('employee_id') or requester.employee_id.id
                )
                vals['department_id'] = (
                    vals.get('department_id')
                    or requester.employee_id.department_id.id
                )
        return super().create(vals_list)

    @api.onchange('requester_id')
    def _onchange_requester_id(self):
        if self.requester_id and self.requester_id.employee_id:
            self.employee_id = self.requester_id.employee_id.id
            self.department_id = self.requester_id.employee_id.department_id.id
        else:
            self.employee_id = False
            self.department_id = False

    @api.model
    def _get_current_cart(self):
        return self.search([
            ('state', '=', 'draft'),
            ('requester_id', '=', self.env.uid),
            ('company_id', '=', self.env.company.id),
        ], limit=1)

    @api.model
    def _get_or_create_cart(self):
        cart = self._get_current_cart()
        if not cart:
            cart = self.create({
                'requester_id': self.env.uid,
                'company_id': self.env.company.id,
            })
        return cart

    def action_submit(self):
        self.ensure_one()
        if not self._is_manager() and self.requester_id != self.env.user:
            raise UserError(_('เฉพาะผู้ขอเท่านั้นที่ส่งคำขอได้'))
        if self.state != 'draft':
            raise UserError(_('เฉพาะคำขอฉบับร่างที่ส่งได้'))
        if not self.line_ids:
            raise UserError(_('กรุณาเพิ่มรายการอย่างน้อย 1 รายการ'))
        for line in self.line_ids:
            if line.requested_qty <= 0:
                raise UserError(_('จำนวนที่ขอของทุกรายการต้องมากกว่า 0'))
        self.with_context(buz_consumable_transition=True).write({
            'name': (
                self.env['ir.sequence'].next_by_code(
                    'buz.it.consumable.request'
                ) or 'New'
            ),
            'state': 'confirmed',
        })
        self.message_post(body=_('คำขอ %s ถูกส่งแล้ว รอการจ่ายของ') % self.name)
        return True

    def action_deliver_all(self):
        self.ensure_one()
        if not self._is_agent():
            raise UserError(_('เฉพาะ Support Agent เท่านั้นที่จ่ายของได้'))
        if self.state not in ('confirmed', 'partial'):
            raise UserError(_('ไม่สามารถจ่ายของในสถานะนี้ได้'))
        blocked = []
        for line in self.line_ids:
            if line.state in ('done', 'rejected'):
                continue
            try:
                line.action_deliver_auto()
            except UserError:
                blocked.append(line)
        if blocked:
            names = ', '.join(
                line.consumable_id.display_name for line in blocked
            )
            raise UserError(_(
                'บางรายการจ่ายไม่ได้ (ต้องเลือก Location หรือของไม่พอ): %s'
            ) % names)
        return True

    def action_cancel(self):
        self.ensure_one()
        if self.state not in ('draft', 'confirmed'):
            raise UserError(_('ไม่สามารถยกเลิกคำขอในสถานะนี้ได้'))
        is_agent = self._is_agent()
        if self.state == 'confirmed' and not is_agent:
            raise UserError(_('เฉพาะ IT เท่านั้นที่ยกเลิกคำขอที่ส่งแล้วได้'))
        if self.state == 'draft' and not (
            is_agent or self.requester_id == self.env.user
        ):
            raise UserError(_('เฉพาะผู้ขอเท่านั้นที่ยกเลิกฉบับร่างได้'))
        self.with_context(buz_consumable_transition=True).write({
            'state': 'cancelled',
        })
        self.message_post(body=_('คำขอ %s ถูกยกเลิก') % self.name)
        return True

    def action_draft(self):
        self.ensure_one()
        if self.state != 'cancelled':
            raise UserError(_('เฉพาะคำขอที่ยกเลิกแล้วที่เปิดใหม่ได้'))
        self.with_context(buz_consumable_transition=True).write({
            'state': 'draft',
            'payer_id': False,
            'pay_date': False,
        })
        return True

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('ลบได้เฉพาะคำขอฉบับร่างเท่านั้น'))
            if not (rec.requester_id == self.env.user or self._is_agent()):
                raise UserError(_('ไม่สามารถลบคำขอนี้ได้'))
        return super().unlink()

    def _recompute_state(self):
        for rec in self:
            if rec.state in ('draft', 'cancelled'):
                continue
            lines = rec.line_ids
            if not lines:
                new_state = 'confirmed'
            else:
                line_states = set(lines.mapped('state'))
                if line_states == {'done'}:
                    new_state = 'done'
                elif line_states == {'rejected'}:
                    new_state = 'rejected'
                elif line_states & {'done', 'partial', 'rejected'}:
                    new_state = 'partial'
                else:
                    new_state = 'confirmed'
            vals = {'state': new_state}
            if new_state == 'done':
                vals.update({
                    'payer_id': rec.payer_id or self.env.user.id,
                    'pay_date': rec.pay_date or fields.Date.context_today(rec),
                })
            elif new_state == 'rejected':
                vals.update({'payer_id': False, 'pay_date': False})
            elif new_state == 'partial':
                vals['pay_date'] = False
            rec.with_context(buz_consumable_transition=True).write(vals)

    def write(self, vals):
        if self.env.context.get('buz_consumable_transition'):
            return super().write(vals)
        protected = {
            'name', 'state', 'requester_id', 'company_id',
            'payer_id', 'pay_date',
        }
        if 'state' in vals:
            raise UserError(_('ใช้ปุ่มสถานะในการเปลี่ยนสถานะเอกสาร'))
        if any(field in vals for field in protected - {'state'}):
            raise UserError(_('ฟิลด์ที่ระบบจัดการไม่สามารถแก้ไขได้'))
        is_agent = self._is_agent()
        if not is_agent:
            for rec in self:
                if not (
                    rec.state == 'draft'
                    and rec.requester_id == self.env.user
                ):
                    raise UserError(_('ไม่สามารถแก้ไขคำขอนี้ได้'))
        return super().write(vals)
