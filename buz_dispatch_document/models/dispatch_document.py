import html as html_lib
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
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    document_date = fields.Date(
        string='Document Date',
        required=True,
        default=lambda self: fields.Date.today() + timedelta(days=1),
        tracking=True,
        help='วันที่เอกสาร — ระบบจะตัดสต็อกอัตโนมัติตามวันที่นี้เมื่อกด Schedule'
    )

    stock_picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery Order',
        required=True,
        ondelete='restrict',
        domain=[('state', 'in', ('confirmed', 'assigned', 'done'))],
        tracking=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        related='stock_picking_id.partner_id',
        string='Customer',
        store=False,
        readonly=True,
    )

    partner_street = fields.Char(
        related='stock_picking_id.partner_id.street',
        string='Street',
        store=False,
        readonly=True,
    )

    partner_street2 = fields.Char(
        related='stock_picking_id.partner_id.street2',
        string='Street 2',
        store=False,
        readonly=True,
    )

    partner_city = fields.Char(
        related='stock_picking_id.partner_id.city',
        string='City',
        store=False,
        readonly=True,
    )

    partner_state_id = fields.Many2one(
        'res.country.state',
        related='stock_picking_id.partner_id.state_id',
        string='State',
        store=False,
        readonly=True,
    )

    partner_zip = fields.Char(
        related='stock_picking_id.partner_id.zip',
        string='ZIP',
        store=False,
        readonly=True,
    )

    partner_phone = fields.Char(
        related='stock_picking_id.partner_id.phone',
        string='Phone',
        store=False,
        readonly=True,
    )

    partner_mobile = fields.Char(
        related='stock_picking_id.partner_id.mobile',
        string='Mobile',
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

    amount_untaxed = fields.Monetary(
        related='stock_picking_id.sale_id.amount_untaxed',
        string='Sale Amount Untaxed',
        readonly=True,
    )

    currency_id = fields.Many2one(
        related='stock_picking_id.sale_id.currency_id',
        string='Currency',
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

    scheduled_date = fields.Datetime(
        related='stock_picking_id.scheduled_date',
        string='Scheduled Date',
        store=False,
        readonly=True,
    )

    vehicle_type = fields.Char(
        related='stock_picking_id.vehicle_type',
        string='Vehicle Type',
        store=False,
        readonly=True,
    )

    vehicle_plate = fields.Char(
        related='stock_picking_id.vehicle_plate',
        string='Vehicle Plate',
        store=False,
        readonly=True,
    )

    driver = fields.Char(
        related='stock_picking_id.driver',
        string='Driver',
        store=False,
        readonly=True,
    )

    dispatch_location = fields.Char(
        related='stock_picking_id.dispatch_location',
        string='Dispatch Location',
        store=False,
        readonly=True,
    )

    sub_district = fields.Char(
        related='stock_picking_id.sub_district',
        string='Sub District',
        store=False,
        readonly=True,
    )

    delivery_note = fields.Text(
        related='stock_picking_id.delivery_note',
        string='Delivery Note',
        store=False,
        readonly=True,
    )

    move_ids_without_package = fields.One2many(
        'stock.move',
        'picking_id',
        string='Stock Moves',
        compute='_compute_move_ids_without_package',
        readonly=True,
    )

    @api.depends('stock_picking_id')
    def _compute_move_ids_without_package(self):
        for record in self:
            record.move_ids_without_package = record.stock_picking_id.move_ids_without_package

    bom_product_html = fields.Html(
        compute='_compute_bom_product_html',
        string='Product Sets',
        sanitize=False,
    )

    @api.depends('stock_picking_id', 'stock_picking_id.move_ids_without_package')
    def _compute_bom_product_html(self):
        for record in self:
            record.bom_product_html = record._get_bom_grouped_html()

    def _get_bom_grouped_html(self):
        picking = self.stock_picking_id
        if not picking:
            return False

        moves = picking.move_ids_without_package
        bom_grouped = {}
        normal_lines = []

        for move in moves:
            bom_line = getattr(move, 'bom_line_id', False)
            if bom_line:
                sale_line = getattr(move, 'sale_line_id', False)
                if sale_line:
                    group_key = f"sale_{sale_line.id}"
                    kit_product = sale_line.product_id
                    kit_uom_name = sale_line.product_uom.name if sale_line.product_uom else ''
                else:
                    group_key = f"bom_{bom_line.bom_id.id}"
                    kit_product = bom_line.bom_id.product_tmpl_id
                    kit_uom_name = kit_product.uom_id.name if kit_product.uom_id else ''

                if group_key not in bom_grouped:
                    bom_grouped[group_key] = {
                        'product': kit_product,
                        'kit_uom_name': kit_uom_name,
                        'moves': [],
                    }
                bom_grouped[group_key]['moves'].append(move)
            else:
                normal_lines.append(move)

        def esc(val):
            return html_lib.escape(str(val or ''))

        rows = []
        line_no = 1

        for move in normal_lines:
            code = esc(move.product_id.default_code)
            name = esc(move.product_id.display_name)
            qty = f'{move.product_uom_qty:.2f}'
            uom = esc(move.product_uom.name)
            rows.append(
                f'<tr>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #eee;">{line_no}</td>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #eee;">{code}</td>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #eee;">{name}</td>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">{qty}</td>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #eee;">{uom}</td>'
                f'</tr>'
            )
            line_no += 1

        for data in bom_grouped.values():
            prod = data['product']
            code = esc(prod.default_code)
            name = esc(prod.name)

            kit_qty = 0.0
            for move in data['moves']:
                bl = move.bom_line_id
                if bl and bl.product_qty:
                    move_kit_qty = move.product_uom_qty * bl.bom_id.product_qty / bl.product_qty
                    if move_kit_qty > kit_qty:
                        kit_qty = move_kit_qty
            qty_str = f'{kit_qty:.2f}' if kit_qty else ''
            uom = esc(data['kit_uom_name'])

            rows.append(
                f'<tr style="background-color:#f8f9fa;">'
                f'<td style="padding:6px 8px;border-bottom:1px solid #dee2e6;font-weight:700;">{line_no}</td>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #dee2e6;font-weight:700;">{code}</td>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #dee2e6;font-weight:700;">'
                f'<i class="fa fa-cube" style="margin-right:4px;color:#714B67;"></i>{name}</td>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #dee2e6;text-align:right;font-weight:700;">{qty_str}</td>'
                f'<td style="padding:6px 8px;border-bottom:1px solid #dee2e6;font-weight:700;">{uom}</td>'
                f'</tr>'
            )
            line_no += 1

            for move in data['moves']:
                comp_code = esc(move.product_id.default_code)
                comp_name = esc(move.product_id.name)
                comp_qty = f'{move.product_uom_qty:.2f}'
                comp_uom = esc(move.product_uom.name)
                rows.append(
                    f'<tr style="color:#6c757d;">'
                    f'<td style="padding:4px 8px;border-bottom:1px solid #eee;"></td>'
                    f'<td style="padding:4px 8px;border-bottom:1px solid #eee;padding-left:16px;">{comp_code}</td>'
                    f'<td style="padding:4px 8px;border-bottom:1px solid #eee;padding-left:24px;">'
                    f'&#8627; {comp_name}</td>'
                    f'<td style="padding:4px 8px;border-bottom:1px solid #eee;text-align:right;">{comp_qty}</td>'
                    f'<td style="padding:4px 8px;border-bottom:1px solid #eee;">{comp_uom}</td>'
                    f'</tr>'
                )

        table = (
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            '<thead><tr>'
            '<th style="padding:8px;border-bottom:2px solid #dee2e6;text-align:left;">#</th>'
            '<th style="padding:8px;border-bottom:2px solid #dee2e6;text-align:left;">Code</th>'
            '<th style="padding:8px;border-bottom:2px solid #dee2e6;text-align:left;">Product</th>'
            '<th style="padding:8px;border-bottom:2px solid #dee2e6;text-align:right;">Qty</th>'
            '<th style="padding:8px;border-bottom:2px solid #dee2e6;text-align:left;">UoM</th>'
            '</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody>'
            '</table>'
        )
        return table

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

    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Only administrators can delete dispatch documents.'))
        return super().unlink()

    # === Action Methods ===
    def action_confirm(self):
        """Backdate stock picking and set dispatch document to done."""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft documents can be confirmed.'))
            if not record.name:
                record.name = self.env['ir.sequence'].next_by_code('buz.dispatch.document')
            picking = record.stock_picking_id
            if picking and picking.state == 'done':
                date_dt = fields.Datetime.to_datetime(record.document_date)
                wiz = self.env['stock.picking.backdate.wiz'].sudo().create({
                    'date': date_dt,
                    'picking_ids': [(6, 0, picking.ids)],
                })
                wiz.change_to_backdate()
            record.state = 'done'
            record.message_post(body=_('Dispatch confirmed. Delivery backdated to %s.') % record.document_date)

    def action_cancel(self):
        """Cancel dispatch document."""
        for record in self:
            if record.state == 'cancel':
                raise UserError(_('Document is already cancelled.'))
            record.state = 'cancel'
            record.message_post(body=_('Dispatch document cancelled.'))

    def action_set_draft(self):
        """Reset cancelled document to draft."""
        for record in self:
            if record.state != 'cancel':
                raise UserError(_('Only cancelled documents can be reset to draft.'))
            record.state = 'draft'

    def action_print_dispatch(self):
        self.ensure_one()
        return self.env.ref('buz_inventory_delivery_report.action_distributor_delivery_export').report_action(self.stock_picking_id)