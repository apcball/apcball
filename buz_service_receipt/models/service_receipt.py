# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ServiceReceipt(models.Model):
    _name = 'service.receipt'
    _description = 'Service Receipt'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'service_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Document Number',
        required=True,
        readonly=True,
        copy=False,
        default='New',
        tracking=True,
    )
    claim_number = fields.Char(
        string='Claim Number',
        readonly=True,
        copy=False,
        default='New',
        tracking=True,
        help='Auto-generated claim number assigned when claim flow starts.',
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('product_return', 'Product Return'),
            ('replacement_delivery', 'Replacement Delivery'),
            ('waiting_replacement', 'Waiting Replacement'),
            ('waiting_invoice', 'Waiting Invoice'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    active = fields.Boolean(default=True)
    form_language = fields.Selection(
        [('th', 'TH'), ('en', 'EN')],
        string='Form Language',
        default=lambda self: 'th' if self.env.lang and self.env.lang.startswith('th') else 'en',
        help='Display language for this service receipt form.',
    )

    informer_name = fields.Char(string='Informer')
    informer_phone = fields.Char(string='Informer Phone')
    request_date = fields.Date(string='Request Date', tracking=True, default=fields.Date.context_today)
    requester_name = fields.Char(string='Service Requester', tracking=True)
    requester_phone = fields.Char(string='Requester Phone')
    warranty_no = fields.Char(string='Warranty Number')
    shop_name = fields.Char(string='Purchased From')
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True)
    service_address = fields.Text(string='Service Address')

    service_date = fields.Date(string='Service Date', tracking=True)
    service_time = fields.Float(string='Service Time')
    schedule_start = fields.Datetime(string='Schedule Start', tracking=True)
    schedule_end = fields.Datetime(string='Schedule End', tracking=True)
    team_id = fields.Many2one(
        'service.team',
        string='Team',
        tracking=True,
    )
    technician_ids = fields.Many2many(
        'res.users',
        'service_receipt_res_users_rel',
        'receipt_id',
        'user_id',
        string='Technicians',
        tracking=True,
    )
    technician_id = fields.Many2one(
        'res.users',
        string='Primary Technician',
        compute='_compute_primary_technician_id',
        inverse='_inverse_primary_technician_id',
        store=True,
        tracking=True,
    )
    calendar_event_id = fields.Many2one('calendar.event', string='Calendar Event', readonly=True, copy=False)
    conflicting_technician_ids = fields.Many2many(
        'res.users',
        compute='_compute_conflicting_technician_ids',
        string='Conflicting Technicians',
    )

    usage_years = fields.Integer(string='Usage Years')
    product_in_warranty = fields.Boolean(string='In Warranty')
    product_out_warranty = fields.Boolean(string='Out of Warranty')
    charge_customer = fields.Boolean(string='Charge Customer')
    appointment_info = fields.Char(string='Other Appointment Info')
    service_case_type = fields.Selection(
        [
            ('service', 'Service'),
            ('replacement', 'Product Replacement'),
            ('out_warranty', 'Out of Warranty'),
        ],
        string='Case Type',
        default='service',
        tracking=True,
    )
    replacement_reason = fields.Text(string='Replacement Reason')
    replacement_date = fields.Date(string='Replacement Date')

    # === Stock Picking Fields (Claim Workflow) ===
    return_picking_id = fields.Many2one(
        'stock.picking', string='Return Picking',
        readonly=True, copy=False,
        help='Stock picking created to receive returned products from customer.',
    )
    return_picking_count = fields.Integer(
        compute='_compute_picking_counts',
        string='Return Picking Count',
    )
    replacement_picking_id = fields.Many2one(
        'stock.picking', string='Replacement Delivery',
        readonly=True, copy=False,
        help='Stock picking created to deliver replacement products to customer.',
    )
    replacement_picking_count = fields.Integer(
        compute='_compute_picking_counts',
        string='Replacement Picking Count',
    )
    picking_count = fields.Integer(
        compute='_compute_picking_counts',
        string='Total Pickings',
    )

    # === Sale Order Field (Out-of-Warranty / Charge Customer) ===
    sale_order_id = fields.Many2one(
        'sale.order', string='Sale Order',
        readonly=True, copy=False,
        help='Sale order created for chargeable service / replacement.',
    )
    sale_order_count = fields.Integer(
        compute='_compute_sale_order_count',
        string='Sale Order Count',
    )

    invoice_id = fields.Many2one('account.move', string='Customer Invoice', readonly=True, copy=False)
    invoice_count = fields.Integer(compute='_compute_invoice_count')
    invoice_status = fields.Selection(
        [
            ('no', 'Nothing to Invoice'),
            ('to_invoice', 'To Invoice'),
            ('invoiced', 'Invoiced'),
            ('paid', 'Paid'),
        ],
        string='Invoice Status',
        compute='_compute_invoice_status',
        store=False,
    )

    change_cancel_by_customer = fields.Boolean(string='Customer Cancelled Appointment')
    change_no_staff = fields.Boolean(string='No Staff Available')
    change_no_parts = fields.Boolean(string='No Spare Parts')
    change_other = fields.Char(string='Other Change Reason')

    service_install_check = fields.Boolean(string='Installation Advice / Inspection')
    service_repair = fields.Boolean(string='Repair / Fix')
    service_install = fields.Boolean(string='Assembly / Installation')
    service_troubleshoot = fields.Boolean(string='Inspection / Advice')
    service_compensation = fields.Boolean(string='Compensation')
    service_other = fields.Char(string='Other Service Job')

    residence_house = fields.Boolean(string='Detached House')
    residence_townhouse = fields.Boolean(string='Townhouse')
    residence_condo = fields.Boolean(string='Condo / Apartment')
    residence_shophouse = fields.Boolean(string='Commercial Building')
    residence_hotel = fields.Boolean(string='Hotel / Resort')
    residence_government = fields.Boolean(string='Government Unit')
    residence_private = fields.Boolean(string='Private Company')
    residence_other = fields.Char(string='Other Residence Type')

    repair_detail = fields.Text(string='Repair Detail')

    install_silicone = fields.Boolean(string='Silicone Work Completed')
    install_accessories = fields.Boolean(string='Accessories Completed')
    install_tested = fields.Boolean(string='Tested Successfully')
    install_site_ready = fields.Boolean(string='Site Ready')

    box_condition = fields.Selection(
        [('good', 'Good'), ('damaged', 'Damaged')],
        string='Box Condition',
    )
    product_condition = fields.Selection(
        [('good', 'Good'), ('damaged', 'Damaged')],
        string='Product Condition',
    )
    accessory_condition = fields.Selection(
        [('complete', 'Complete'), ('incomplete', 'Incomplete')],
        string='Accessory Condition',
    )

    summary_installation = fields.Boolean(string='Installation')
    summary_usage = fields.Boolean(string='Usage')
    summary_sanitary = fields.Boolean(string='Sanitary System')
    summary_unknown = fields.Boolean(string='Unknown Cause')
    summary_quality = fields.Boolean(string='Product Quality')
    summary_transport = fields.Boolean(string='Transportation')
    summary_lifetime = fields.Boolean(string='Lifetime')
    summary_other = fields.Char(string='Other Summary')

    suggestion = fields.Text(string='Additional Suggestion')
    note = fields.Text(string='Remark')

    service_by_name = fields.Char(string='Service Provider')
    service_by_date = fields.Date(string='Service Provider Date')
    customer_sign_name = fields.Char(string='Service Receiver')
    customer_sign_date = fields.Date(string='Service Receiver Date')
    approver_name = fields.Char(string='Approver')

    line_ids = fields.One2many('service.receipt.line', 'receipt_id', string='Products')
    line_count = fields.Integer(compute='_compute_line_count')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    @api.depends('return_picking_id', 'replacement_picking_id')
    def _compute_picking_counts(self):
        for record in self:
            record.return_picking_count = 1 if record.return_picking_id else 0
            record.replacement_picking_count = 1 if record.replacement_picking_id else 0
            record.picking_count = record.return_picking_count + record.replacement_picking_count

    @api.depends('sale_order_id')
    def _compute_sale_order_count(self):
        for record in self:
            record.sale_order_count = 1 if record.sale_order_id else 0

    @api.depends('technician_ids')
    def _compute_primary_technician_id(self):
        for record in self:
            record.technician_id = record.technician_ids[:1].id if record.technician_ids else False

    @api.depends('technician_ids', 'schedule_start', 'schedule_end', 'state')
    def _compute_conflicting_technician_ids(self):
        for record in self:
            record.conflicting_technician_ids = [(6, 0, record._get_conflicting_technicians().ids)]

    def _inverse_primary_technician_id(self):
        for record in self:
            if record.technician_id:
                if record.technician_id not in record.technician_ids:
                    record.technician_ids = [(6, 0, [record.technician_id.id] + record.technician_ids.ids)]
            else:
                record.technician_ids = [(5, 0, 0)]

    @api.depends('invoice_id')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = 1 if record.invoice_id else 0

    @api.depends('invoice_id', 'line_ids.bill_customer', 'line_ids.price_unit', 'charge_customer')
    def _compute_invoice_status(self):
        for record in self:
            if record.invoice_id:
                record.invoice_status = 'paid' if record.invoice_id.payment_state == 'paid' else 'invoiced'
            elif record._get_billable_lines() or record.charge_customer:
                record.invoice_status = 'to_invoice'
            else:
                record.invoice_status = 'no'

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            if not self.requester_name:
                self.requester_name = self.partner_id.name
            if not self.requester_phone:
                self.requester_phone = self.partner_id.phone or self.partner_id.mobile
            if not self.service_address:
                self.service_address = self.partner_id.contact_address

    @api.onchange('team_id')
    def _onchange_team_id(self):
        if self.team_id:
            self.technician_ids = [(6, 0, self.team_id.member_ids.ids)]

    @api.onchange('service_date', 'service_time')
    def _onchange_service_schedule(self):
        if self.service_date:
            raw = self.service_time or 0.0
            total_minutes = int(round(raw * 60))
            hour = (total_minutes // 60) % 24
            minute = total_minutes % 60
            self.schedule_start = fields.Datetime.to_datetime(
                f"{self.service_date} {hour:02d}:{minute:02d}:00"
            )
            if not self.schedule_end:
                self.schedule_end = fields.Datetime.add(self.schedule_start, hours=2)

    @api.onchange('technician_ids', 'schedule_start', 'schedule_end', 'state')
    def _onchange_technician_schedule_conflicts(self):
        conflicting_technicians = self._get_conflicting_technicians()
        if conflicting_technicians:
            self.technician_ids = [(6, 0, (self.technician_ids - conflicting_technicians).ids)]
            return {
                'warning': {
                    'title': _('Technician Schedule Conflict'),
                    'message': _(
                        'These technicians were removed because they already have overlapping service jobs: %s'
                    ) % ', '.join(conflicting_technicians.mapped('name')),
                }
            }
        return {}

    @api.constrains('schedule_start', 'schedule_end')
    def _check_schedule_dates(self):
        for record in self:
            if record.schedule_start and record.schedule_end and record.schedule_end < record.schedule_start:
                raise ValidationError(_('Schedule end must be after schedule start.'))

    @api.constrains('technician_ids', 'schedule_start', 'schedule_end', 'state')
    def _check_technician_schedule_conflicts(self):
        for record in self:
            conflicting_technicians = record._get_conflicting_technicians()
            if conflicting_technicians:
                raise ValidationError(_(
                    'These technicians already have overlapping service jobs: %s'
                ) % ', '.join(conflicting_technicians.mapped('name')))

    @api.model
    def create(self, vals):
        is_claim = vals.get('service_case_type') == 'replacement'
        if is_claim:
            if not vals.get('claim_number') or vals.get('claim_number') == 'New':
                vals['claim_number'] = self.env['ir.sequence'].next_by_code('service.claim') or 'New'
            if not vals.get('name') or vals.get('name') == 'New':
                vals['name'] = vals.get('claim_number', 'New')
        else:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('service.receipt') or 'New'
        record = super().create(vals)
        record._sync_calendar_event()
        return record

    def write(self, vals):
        if vals.get('service_case_type') == 'replacement':
            new_claim = False
            for record in self:
                if not record.claim_number or record.claim_number == 'New':
                    if not new_claim:
                        new_claim = self.env['ir.sequence'].next_by_code('service.claim') or 'New'
                    if new_claim:
                        record.write({'claim_number': new_claim})
        result = super().write(vals)
        tracked_fields = {
            'name', 'requester_name', 'partner_id', 'service_address', 'schedule_start',
            'schedule_end', 'technician_id', 'technician_ids', 'state', 'active',
        }
        if tracked_fields.intersection(vals):
            self._sync_calendar_event()
        return result

    def unlink(self):
        events = self.mapped('calendar_event_id')
        result = super().unlink()
        if events:
            events.unlink()
        return result

    def _get_conflict_domain(self):
        self.ensure_one()
        if not self.technician_ids or not self.schedule_start:
            return []
        schedule_end = self.schedule_end or self.schedule_start
        return [
            ('id', '!=', self.id or 0),
            ('state', '!=', 'cancel'),
            ('schedule_start', '!=', False),
            ('schedule_end', '!=', False),
            ('technician_ids', 'in', self.technician_ids.ids),
            ('schedule_start', '<', schedule_end),
            ('schedule_end', '>', self.schedule_start),
        ]

    def _get_conflicting_technicians(self):
        self.ensure_one()
        domain = self._get_conflict_domain()
        if not domain:
            return self.env['res.users']
        conflicting_receipts = self.search(domain)
        return conflicting_receipts.mapped('technician_ids').filtered(lambda user: user in self.technician_ids)

    def _prepare_calendar_event_vals(self):
        self.ensure_one()
        partner_ids = list(self.partner_id.ids)
        partner_ids.extend(self.technician_ids.mapped('partner_id').ids)
        employee_partners = self.company_id.service_receipt_attendee_employee_ids.mapped('user_id.partner_id').ids
        partner_ids.extend(employee_partners)
        partner_ids = list(dict.fromkeys(partner_ids))
        description_parts = [
            _('Service Receipt: %s') % self.name,
            _('Requester: %s') % (self.requester_name or '-'),
            _('Phone: %s') % (self.requester_phone or '-'),
            _('Address: %s') % (self.service_address or '-'),
            _('Repair Detail: %s') % (self.repair_detail or '-'),
        ]
        return {
            'name': '%s - %s' % (self.name, self.requester_name or _('Service Job')),
            'start': self.schedule_start,
            'stop': self.schedule_end or self.schedule_start,
            'allday': False,
            'description': '\n'.join(description_parts),
            'user_id': self.technician_id.id or self.env.user.id,
            'partner_ids': [(6, 0, partner_ids)],
        }

    def _sync_calendar_event(self):
        for record in self:
            if record.state == 'cancel' or not record.schedule_start:
                if record.calendar_event_id:
                    record.calendar_event_id.unlink()
                    record.calendar_event_id = False
                continue

            vals = record._prepare_calendar_event_vals()
            if record.calendar_event_id:
                record.calendar_event_id.write(vals)
            else:
                record.calendar_event_id = self.env['calendar.event'].create(vals)

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def _generate_claim_number(self):
        for record in self:
            if not record.claim_number or record.claim_number == 'New':
                record.claim_number = self.env['ir.sequence'].next_by_code('service.claim') or 'New'

    def action_waiting_replacement(self):
        self._generate_claim_number()
        self.write({'state': 'product_return', 'service_case_type': 'replacement'})

    def action_waiting_invoice(self):
        self.write({'state': 'waiting_invoice', 'service_case_type': 'out_warranty', 'charge_customer': True})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})

    # ==================== Return Picking Actions ====================

    def _get_claim_return_location(self):
        """Get or create the claim return location for receiving returned products."""
        location = self.env.ref('buz_service_receipt.stock_location_claim_return', raise_if_not_found=False)
        if not location:
            warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
            parent_location = warehouse.lot_stock_id if warehouse else self.env.ref('stock.stock_location_stock')
            location = self.env['stock.location'].create({
                'name': 'Claim Return',
                'usage': 'internal',
                'location_id': parent_location.id,
            })
        return location

    def _get_claim_picking_type(self, picking_type_code='incoming'):
        """Get the claim picking type."""
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
        if not warehouse:
            if picking_type_code == 'incoming':
                return self.env.ref('stock.picking_type_in')
            else:
                return self.env.ref('stock.picking_type_out')
        if picking_type_code == 'incoming':
            return warehouse.in_type_id
        else:
            return warehouse.out_type_id

    def _prepare_return_move_vals(self, line):
        """Prepare stock move values for a return line."""
        product = line.product_id
        if not product:
            raise UserError(_('Please specify a product on line %s.') % line.sequence)
        location_src = self.partner_id.property_stock_customer if self.partner_id else self.env.ref('stock.stock_location_customers')
        location_dest = self._get_claim_return_location()
        return {
            'name': _('Claim Return: %s') % self.name,
            'product_id': product.id,
            'product_uom_qty': line.quantity,
            'product_uom': product.uom_id.id,
            'location_id': location_src.id,
            'location_dest_id': location_dest.id,
        }

    def _prepare_replacement_move_vals(self, line):
        """Prepare stock move values for a replacement delivery line."""
        product = line.replacement_product_id
        if not product:
            raise UserError(_('Please specify a replacement product on line %s.') % line.sequence)
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
        location_src = warehouse.lot_stock_id if warehouse else self.env.ref('stock.stock_location_stock')
        location_dest = self.partner_id.property_stock_customer if self.partner_id else self.env.ref('stock.stock_location_customers')
        return {
            'name': _('Replacement Delivery: %s') % self.name,
            'product_id': product.id,
            'product_uom_qty': line.replacement_qty or line.quantity,
            'product_uom': product.uom_id.id,
            'location_id': location_src.id,
            'location_dest_id': location_dest.id,
        }

    def action_create_return_picking(self):
        """Create stock picking to receive returned products from customer."""
        self.ensure_one()
        if self.return_picking_id:
            return self.action_view_return_picking()
        if not self.partner_id:
            raise UserError(_('Please select a customer first.'))
        replacement_lines = self.line_ids.filtered(lambda l: l.product_id)
        if not replacement_lines:
            raise UserError(_('No products specified on lines.'))

        move_vals_list = [self._prepare_return_move_vals(line) for line in replacement_lines]
        picking = self.env['stock.picking'].create({
            'partner_id': self.partner_id.id,
            'location_id': self.partner_id.property_stock_customer.id,
            'location_dest_id': self._get_claim_return_location().id,
            'picking_type_id': self._get_claim_picking_type('incoming').id,
            'move_ids_without_package': [(0, 0, vals) for vals in move_vals_list],
            'origin': self.name,
        })
        picking.action_confirm()
        picking.action_assign()
        self.write({
            'return_picking_id': picking.id,
            'state': 'product_return',
        })
        self.message_post(body=_('Return picking created: %s') % picking.name)
        return self.action_view_return_picking()

    def action_view_return_picking(self):
        self.ensure_one()
        if not self.return_picking_id:
            raise UserError(_('No return picking has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return Picking'),
            'res_model': 'stock.picking',
            'res_id': self.return_picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ==================== Replacement Delivery Actions ====================

    def action_create_replacement_picking(self):
        """Create stock picking to deliver replacement products to customer."""
        self.ensure_one()
        if self.replacement_picking_id:
            return self.action_view_replacement_picking()
        if not self.partner_id:
            raise UserError(_('Please select a customer first.'))
        replacement_lines = self.line_ids.filtered(
            lambda l: l.replacement_product_id
        )
        if not replacement_lines:
            raise UserError(_('No lines with a replacement product specified.'))

        move_vals_list = [self._prepare_replacement_move_vals(line) for line in replacement_lines]
        picking = self.env['stock.picking'].create({
            'partner_id': self.partner_id.id,
            'location_id': self._get_claim_return_location().id,
            'location_dest_id': self.partner_id.property_stock_customer.id,
            'picking_type_id': self._get_claim_picking_type('outgoing').id,
            'move_ids_without_package': [(0, 0, vals) for vals in move_vals_list],
            'origin': self.name,
        })
        picking.action_confirm()
        picking.action_assign()
        self.write({
            'replacement_picking_id': picking.id,
            'state': 'replacement_delivery',
        })
        self.message_post(body=_('Replacement delivery created: %s') % picking.name)
        return self.action_view_replacement_picking()

    def action_view_replacement_picking(self):
        self.ensure_one()
        if not self.replacement_picking_id:
            raise UserError(_('No replacement delivery has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Replacement Delivery'),
            'res_model': 'stock.picking',
            'res_id': self.replacement_picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ==================== Sale Order Actions ====================

    def _prepare_sale_order_vals(self):
        """Prepare sale order values for chargeable service/replacement."""
        self.ensure_one()
        billable_lines = self._get_billable_lines()
        order_lines = []
        for line in billable_lines:
            product = line.replacement_product_id or line.product_id
            order_lines.append((0, 0, {
                'product_id': product.id,
                'name': line.invoice_description or line.description or product.display_name,
                'product_uom_qty': line.invoice_qty or line.quantity or 1.0,
                'price_unit': line.price_unit,
            }))
        return {
            'partner_id': self.partner_id.id,
            'origin': self.name,
            'user_id': self.technician_id.id or self.env.user.id,
            'order_line': order_lines,
            'company_id': self.company_id.id,
        }

    def action_create_sale_order(self):
        """Create a sale order for chargeable service/replacement."""
        self.ensure_one()
        if self.sale_order_id:
            return self.action_view_sale_order()
        if not self.partner_id:
            raise UserError(_('Please select a customer before creating a sale order.'))
        billable_lines = self._get_billable_lines()
        if not billable_lines and not self.charge_customer:
            raise UserError(_('No billable lines found. Mark lines as billable and set a unit price.'))
        if not billable_lines:
            raise UserError(_('Please mark at least one line as billable and set a unit price.'))

        sale_order = self.env['sale.order'].create(self._prepare_sale_order_vals())
        self.write({
            'sale_order_id': sale_order.id,
        })
        self.message_post(body=_('Sale order created: %s') % sale_order.name)
        return self.action_view_sale_order()

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_('No sale order has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order'),
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ==================== View All Pickings ====================

    def action_view_pickings(self):
        """View all related stock pickings (return + replacement)."""
        self.ensure_one()
        pickings = self.return_picking_id + self.replacement_picking_id
        if not pickings:
            raise UserError(_('No pickings have been created yet.'))
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', pickings.ids)]
        action['context'] = {}
        return action

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('buz_service_receipt.action_report_service_receipt').report_action(self)

    def action_print_repair_notification_pdf(self):
        self.ensure_one()
        return self.env.ref('buz_service_receipt.action_report_service_repair_notification').report_action(self)

    def action_print_claim_pdf(self):
        self.ensure_one()
        return self.env.ref('buz_service_receipt.action_report_service_claim').report_action(self)

    def _get_billable_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda l: l.bill_customer and l.price_unit > 0 and (l.replacement_product_id or l.product_id))

    def action_create_customer_invoice(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('Please select a customer before creating an invoice.'))
        if self.invoice_id:
            return self.action_view_invoice()

        billable_lines = self._get_billable_lines()
        if not billable_lines:
            raise UserError(_('Please mark at least one line as billable and set a unit price.'))

        invoice_lines = []
        for line in billable_lines:
            product = line.replacement_product_id or line.product_id
            invoice_lines.append((0, 0, {
                'product_id': product.id,
                'name': line.invoice_description or line.description or product.display_name,
                'quantity': line.invoice_qty or line.quantity or 1.0,
                'price_unit': line.price_unit,
            }))

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name,
            'invoice_user_id': self.technician_id.id or self.env.user.id,
            'invoice_line_ids': invoice_lines,
        })
        self.write({
            'invoice_id': invoice.id,
            'state': 'waiting_invoice' if invoice.state == 'draft' else self.state,
        })
        self.message_post(body=_('Customer invoice created: %s') % invoice.name)
        return self.action_view_invoice()

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No customer invoice has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class ServiceReceiptLine(models.Model):
    _name = 'service.receipt.line'
    _description = 'Service Receipt Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    receipt_id = fields.Many2one('service.receipt', string='Service Receipt', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product')
    description = fields.Char(string='Product Description')
    quantity = fields.Float(string='Quantity', default=1.0)
    issue_detail = fields.Text(string='Reported Problem')
    appointment_detail = fields.Text(string='Appointment Detail')
    product_detail = fields.Text(string='Product Detail')
    resolution_type = fields.Selection(
        [
            ('repair', 'Repair'),
            ('replace', 'Replace'),
            ('service', 'Service Charge'),
        ],
        string='Resolution',
        default='repair',
    )
    replacement_product_id = fields.Many2one('product.product', string='Replacement Product')
    replacement_qty = fields.Float(string='Replacement Qty', default=1.0)
    bill_customer = fields.Boolean(string='Bill Customer')
    invoice_qty = fields.Float(string='Invoice Qty', default=1.0)
    price_unit = fields.Float(string='Unit Price')
    invoice_description = fields.Char(string='Invoice Description')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id and not self.description:
            self.description = self.product_id.display_name
        if self.product_id and not self.invoice_description:
            self.invoice_description = self.product_id.display_name

    @api.onchange('replacement_product_id')
    def _onchange_replacement_product_id(self):
        if self.replacement_product_id and not self.invoice_description:
            self.invoice_description = self.replacement_product_id.display_name
        if self.resolution_type == 'replace' and not self.invoice_qty:
            self.invoice_qty = self.replacement_qty or 1.0
