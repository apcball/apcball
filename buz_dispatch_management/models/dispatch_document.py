from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class BuzDispatchDocument(models.Model):
    _name = 'buz.dispatch.document'
    _description = 'Dispatch Document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'dispatch_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string='Dispatch Number', readonly=True, copy=False, tracking=True)
    active = fields.Boolean(default=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('printed', 'Printed'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)

    dispatch_date = fields.Date(
        string='Dispatch Date',
        required=True,
        default=lambda self: fields.Date.today(),
        tracking=True,
    )

    posted_date = fields.Datetime(
        string='Posted Date',
        readonly=True,
        copy=False,
        tracking=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        readonly=True,
        tracking=True,
    )

    sale_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        readonly=True,
    )

    picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery Order',
        required=True,
        ondelete='restrict',
        domain=[('state', 'in', ('confirmed', 'assigned', 'done'))],
        tracking=True,
    )

    driver_name = fields.Char(string='Driver Name', tracking=True)
    vehicle_no = fields.Char(string='Vehicle No.')

    receiver_name = fields.Char(string='Receiver Name', tracking=True)
    receiver_signature = fields.Binary(string='Receiver Signature')

    origin = fields.Char(
        string='Source Document',
        related='picking_id.origin',
        readonly=True,
    )

    scheduled_date = fields.Datetime(
        string='Scheduled Date',
        related='picking_id.scheduled_date',
        readonly=True,
    )

    date_deadline = fields.Datetime(
        string='Deadline',
        related='picking_id.date_deadline',
        readonly=True,
    )

    partner_phone = fields.Char(
        string='Phone',
        related='partner_id.phone',
        readonly=True,
    )

    partner_mobile = fields.Char(
        string='Mobile',
        related='partner_id.mobile',
        readonly=True,
    )

    partner_email = fields.Char(
        string='Email',
        related='partner_id.email',
        readonly=True,
    )

    partner_address = fields.Char(
        string='Address',
        related='partner_id.contact_address',
        readonly=True,
    )

    weight = fields.Float(
        string='Total Weight',
        related='picking_id.weight',
        readonly=True,
    )

    number_of_packages = fields.Integer(
        string='Packages',
        related='picking_id.number_of_packages',
        readonly=True,
    )

    note = fields.Text(string='Note')

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'buz_dispatch_document_attachment_rel',
        'doc_id',
        'attachment_id',
        string='Attachments',
    )

    line_ids = fields.One2many(
        'buz.dispatch.document.line',
        'dispatch_id',
        string='Dispatch Lines',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    print_count = fields.Integer(
        string='Print Count',
        default=0,
        copy=False,
    )

    first_print_date = fields.Datetime(
        string='First Print Date',
        readonly=True,
        copy=False,
    )

    last_print_date = fields.Datetime(
        string='Last Print Date',
        readonly=True,
        copy=False,
    )

    printed_by = fields.Many2one(
        'res.users',
        string='Printed By',
        readonly=True,
        copy=False,
    )

    remaining_qty = fields.Float(
        string='Remaining Quantity',
        compute='_compute_remaining_qty',
    )

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Dispatch number must be unique!'),
    ]

    @api.depends('picking_id', 'line_ids.dispatch_qty')
    def _compute_remaining_qty(self):
        for doc in self:
            if not doc.picking_id:
                doc.remaining_qty = 0.0
                continue
            total_ordered = sum(doc.picking_id.move_ids.mapped('product_uom_qty'))
            total_dispatched = sum(doc.line_ids.mapped('dispatch_qty'))
            existing = self.search([
                ('picking_id', '=', doc.picking_id.id),
                ('state', '!=', 'cancel'),
                ('id', '!=', doc.id),
            ])
            total_dispatched += sum(existing.line_ids.mapped('dispatch_qty'))
            doc.remaining_qty = total_ordered - total_dispatched

    @api.constrains('state')
    def _check_state_transitions(self):
        for doc in self:
            if doc.state == 'posted' and doc.picking_id.state != 'done':
                raise ValidationError(
                    _('Cannot set state to posted: the delivery order is not validated.')
                )

    def unlink(self):
        posted = self.filtered(lambda d: d.state == 'posted')
        if posted:
            raise UserError(_('Cannot delete posted dispatch documents.'))
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('dispatch_date'):
                vals['dispatch_date'] = fields.Date.today()
            if not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code('buz.dispatch.document')
        records = super().create(vals_list)
        for record in records:
            record.message_post(body=_('Dispatch Document %s created.') % record.name)
        return records

    def action_print(self):
        self.ensure_one()
        now = fields.Datetime.now()
        self.write({
            'print_count': self.print_count + 1,
            'first_print_date': self.first_print_date or now,
            'last_print_date': now,
            'printed_by': self.env.user.id,
        })
        if self.state == 'draft':
            self.state = 'printed'
        self.message_post(
            body=_('Document printed by %s.') % self.env.user.display_name
        )
        return self.env.ref('buz_dispatch_management.action_report_dispatch_document').report_action(self)

    def action_open_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_deliver(self):
        self.ensure_one()
        if self.state != 'in_transit':
            raise UserError(_('Only documents in transit can be marked as delivered.'))
        self.state = 'delivered'
        self.message_post(body=_('Goods marked as delivered.'))

    def action_post(self):
        self.ensure_one()
        if self.state == 'posted':
            raise UserError(_('Document is already posted.'))
        if self.state == 'cancel':
            raise UserError(_('Cannot post a cancelled document.'))
        if self.state not in ('delivered', 'in_transit'):
            raise UserError(_('Document must be delivered before posting.'))

        picking = self.picking_id
        if picking.state == 'done':
            self.write({
                'state': 'posted',
                'posted_date': fields.Datetime.now(),
            })
            self.message_post(body=_('Document posted. Delivery was already validated.'))
            return

        if picking.state == 'draft':
            picking.action_confirm()
        if picking.state in ('confirmed', 'assigned'):
            picking.button_validate()

        self.write({
            'state': 'posted',
            'posted_date': fields.Datetime.now(),
        })
        self.message_post(body=_('Document posted. Stock deducted via %s.') % picking.name)

    def action_cancel(self):
        self.ensure_one()
        if self.state == 'posted':
            raise UserError(_('Cannot cancel a posted document.'))
        if self.state == 'cancel':
            raise UserError(_('Document is already cancelled.'))
        self.state = 'cancel'
        self.message_post(body=_('Document cancelled.'))

    def action_set_draft(self):
        self.ensure_one()
        if self.state == 'posted':
            raise UserError(_('Cannot reset a posted document to draft.'))
        self.state = 'draft'
        self.message_post(body=_('Document reset to draft.'))

    def action_in_transit(self):
        self.ensure_one()
        if self.state not in ('draft', 'printed'):
            raise UserError(_('Only draft or printed documents can be moved to in transit.'))
        self.state = 'in_transit'
        self.message_post(body=_('Document marked as in transit.'))

    def cron_auto_post(self):
        today = fields.Date.today()
        docs = self.search([
            ('state', '=', 'delivered'),
            ('dispatch_date', '<', today),
        ])
        success_count = 0
        fail_count = 0
        for doc in docs:
            try:
                doc.action_post()
                doc.message_post(body=_('Auto-posted by scheduled action.'))
                success_count += 1
            except Exception as e:
                doc.message_post(body=_('Auto-posting failed: %s') % str(e))
                fail_count += 1
        if docs:
            self.env['bus.bus']._sendone(
                self.env.user.partner_id,
                'simple_notification',
                {
                    'title': _('Auto-Post Results'),
                    'message': _('%d posted, %d failed') % (success_count, fail_count),
                    'type': 'info',
                    'sticky': False,
                }
            )
        return True
