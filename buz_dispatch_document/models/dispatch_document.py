from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class BuzDispatchDocument(models.Model):
    _name = 'buz.dispatch.document'
    _description = 'Dispatch Document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'document_date desc, id desc'
    _rec_name = 'name'

    # === Fields ===
    name = fields.Char(string='Dispatch Number', readonly=True, copy=False, tracking=True)
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
    ], string='Status', default='draft', tracking=True)

    document_date = fields.Date(
        string='Document Date',
        required=True,
        default=lambda self: fields.Date.today() + timedelta(days=1),
        tracking=True,
        help='วันที่เอกสาร อ้างอิงสำหรับการตัดสต็อก (Auto: วันถัดไป)'
    )

    stock_picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery Order',
        required=True,
        ondelete='restrict',
        domain=[('state', 'in', ('confirmed', 'assigned'))],
        tracking=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        related='stock_picking_id.partner_id',
        string='Customer',
        store=False,
        readonly=True,
    )

    sale_id = fields.Many2one(
        'sale.order',
        related='stock_picking_id.sale_id',
        string='Sale Order',
        store=False,
        readonly=True,
    )

    origin = fields.Char(
        related='stock_picking_id.origin',
        string='Source Document',
        store=False,
        readonly=True,
    )

    picking_state = fields.Selection(
        related='stock_picking_id.state',
        string='Picking Status',
        store=False,
        readonly=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    # === SQL Constraints ===
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Dispatch number must be unique!'),
    ]

    # === CRUD ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('document_date'):
                vals['document_date'] = fields.Date.today() + timedelta(days=1)
        return super().create(vals_list)

    # === Action Methods ===
    def action_confirm(self):
        """Run sequence number and set state to confirmed"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft documents can be confirmed.'))
            if not record.name:
                record.name = self.env['ir.sequence'].next_by_code('buz.dispatch.document')
            record.state = 'confirmed'

    def action_validate(self):
        """Validate the source stock picking and set state to done"""
        for record in self:
            if record.state != 'confirmed':
                raise UserError(_('Only confirmed documents can be validated.'))
            picking = record.stock_picking_id
            if picking.state == 'draft':
                picking.action_confirm()
            if picking.state in ('confirmed', 'assigned'):
                picking.button_validate()
            record.state = 'done'

    def action_set_draft(self):
        """Reset to draft"""
        for record in self:
            if record.state != 'confirmed':
                raise UserError(_('Only confirmed documents can be reset to draft.'))
            record.state = 'draft'

    def action_validate_cron(self):
        """Cron method: auto-validate dispatch documents that are confirmed and due"""
        today = fields.Date.today()
        documents = self.search([
            ('state', '=', 'confirmed'),
            ('document_date', '<=', today),
        ])
        for doc in documents:
            try:
                doc.action_validate()
                doc.message_post(body=_('Auto-validated by cron job at 05:00.'))
            except Exception as e:
                doc.message_post(
                    body=_('Auto-validation failed: %s', str(e))
                )
        return True