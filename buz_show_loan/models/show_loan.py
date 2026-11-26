from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


def operation_marker(picking_type):
    return ' '.join(filter(None, (
        picking_type.sequence_code,
        picking_type.sequence_id.prefix,
    ))).upper()


class ShowLoan(models.Model):
    _name = 'buz.show.loan'
    _description = 'Show Loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(default='New', readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner', string='Contact', required=True, check_company=True)
    picking_type_id = fields.Many2one('stock.picking.type', string='Operation Type',
                                      required=True, check_company=True,
                                      domain="[('code', '=', 'internal'), ('company_id', '=', company_id)]")
    requisition_order = fields.Char(string='Requisition Order')
    location_id = fields.Many2one('stock.location', string='Source Location',
                                  related='picking_type_id.default_location_src_id', readonly=True)
    location_dest_id = fields.Many2one('stock.location', string='Destination Location', required=True,
                                       check_company=True, domain="[('usage', '=', 'internal')]")
    scheduled_date = fields.Datetime(string='Scheduled Date', required=True,
                                     default=fields.Datetime.now)
    origin = fields.Char(string='Source Document')
    tag_ids = fields.Many2many('buz.picking.tag', string='Tags')
    analytic_auto_sync = fields.Boolean(string='Auto Sync Analytic', default=True)
    line_ids = fields.One2many('buz.show.loan.line', 'loan_id', string='Products', copy=True)
    picking_id = fields.Many2one('stock.picking', readonly=True, copy=False, check_company=True)
    picking_ids = fields.One2many('stock.picking', 'show_loan_id', string='Transfers')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'),
                              ('cancel', 'Cancelled')], default='draft', readonly=True, tracking=True)

    def write(self, vals):
        protected = {'company_id', 'partner_id', 'picking_type_id', 'requisition_order',
                     'location_dest_id', 'scheduled_date', 'origin', 'tag_ids',
                     'analytic_auto_sync', 'line_ids'}
        if protected.intersection(vals) and any(loan.state != 'draft' for loan in self):
            raise UserError(_('A confirmed loan cannot be edited.'))
        return super().write(vals)

    def unlink(self):
        if any(loan.state != 'draft' for loan in self):
            raise UserError(_('Only draft loans can be deleted.'))
        return super().unlink()

    def action_confirm(self):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM buz_show_loan WHERE id = %s FOR UPDATE', [self.id])
        self.env.invalidate_all()
        if self.state != 'draft' or self.picking_id:
            raise UserError(_('Only a new draft loan can be confirmed.'))
        if not self.line_ids:
            raise ValidationError(_('Add at least one product.'))
        picking_type = self.picking_type_id
        markers = [code for code in ('BG-PJ', 'BG-RT', 'BG-OL')
                   if code in operation_marker(picking_type)]
        if (not picking_type.active or picking_type.code != 'internal'
                or len(markers) != 1 or picking_type.company_id != self.company_id):
            raise ValidationError(_('Select one active BG-PJ, BG-RT or BG-OL Internal Transfer type for this company.'))
        source = picking_type.default_location_src_id
        if source.complete_name != 'FG10/Stock' or source.company_id not in (self.company_id, False):
            raise ValidationError(_('The BG Operation Type must start at FG10/Stock.'))
        dest = self.location_dest_id
        if (dest.usage != 'internal' or dest == source
                or dest.company_id not in (self.company_id, False)):
            raise ValidationError(_('Select a different internal loan location in this company.'))

        picking_vals = {
            'picking_type_id': picking_type.id,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'location_id': source.id,
            'location_dest_id': dest.id,
            'scheduled_date': self.scheduled_date,
            'origin': self.origin or False,
            'tag_ids': [Command.set(self.tag_ids.ids)],
            'show_loan_id': self.id,
            'show_loan_role': 'loan',
            'move_ids_without_package': [Command.create({
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom': line.uom_id.id,
                'product_uom_qty': line.qty_requested,
                'location_id': source.id,
                'location_dest_id': dest.id,
                'company_id': self.company_id.id,
                'show_loan_line_id': line.id,
            }) for line in self.line_ids],
        }
        for field_name in ('requisition_order', 'analytic_auto_sync'):
            if field_name in self.env['stock.picking']._fields:
                picking_vals[field_name] = self[field_name]
        picking = self.env['stock.picking'].create(picking_vals)
        picking.action_confirm()
        self.write({'picking_id': picking.id, 'name': picking.name, 'state': 'confirmed'})
        return self.action_open_pickings()

    def action_create_return(self):
        self.ensure_one()
        if self.state != 'confirmed' or not any(line.qty_available > 0 for line in self.line_ids):
            raise UserError(_('No issued products are available to return.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Show Return'),
            'res_model': 'buz.show.loan.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_loan_id': self.id},
        }

    def action_open_pickings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Show Loan Transfers'),
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': [('show_loan_id', '=', self.id)],
        }

    def action_cancel(self):
        for loan in self:
            if any(p.state == 'done' for p in loan.picking_ids):
                raise UserError(_('A loan with completed transfers cannot be cancelled.'))
            loan.picking_ids.filtered(lambda p: p.state != 'cancel').action_cancel()
            loan.write({'state': 'cancel'})


class ShowLoanLine(models.Model):
    _name = 'buz.show.loan.line'
    _description = 'Show Loan Line'
    _check_company_auto = True

    loan_id = fields.Many2one('buz.show.loan', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='loan_id.company_id', store=True)
    product_id = fields.Many2one('product.product', required=True, check_company=True)
    uom_id = fields.Many2one('uom.uom', required=True)
    qty_requested = fields.Float(string='Loan Quantity', required=True, digits='Product Unit of Measure')
    move_ids = fields.One2many('stock.move', 'show_loan_line_id')
    qty_issued = fields.Float(compute='_compute_quantities', digits='Product Unit of Measure')
    qty_returned = fields.Float(compute='_compute_quantities', digits='Product Unit of Measure')
    qty_available = fields.Float(compute='_compute_quantities', digits='Product Unit of Measure')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id

    @api.constrains('product_id', 'uom_id', 'qty_requested')
    def _check_line(self):
        for line in self:
            if line.uom_id.category_id != line.product_id.uom_id.category_id:
                raise ValidationError(_('The unit of measure must match the product.'))
            if float_compare(line.qty_requested, 0, precision_rounding=line.uom_id.rounding) <= 0:
                raise ValidationError(_('Loan quantity must be positive.'))

    @api.model_create_multi
    def create(self, vals_list):
        loans = self.env['buz.show.loan'].browse([
            vals['loan_id'] for vals in vals_list if vals.get('loan_id')
        ])
        if any(loan.state != 'draft' for loan in loans):
            raise UserError(_('A confirmed loan line cannot be added.'))
        return super().create(vals_list)

    @api.depends('move_ids.state', 'move_ids.quantity', 'move_ids.product_uom_qty',
                 'move_ids.picking_id.state', 'move_ids.picking_id.show_loan_role')
    def _compute_quantities(self):
        for line in self:
            issued = returned = pending = 0.0
            for move in line.move_ids:
                if move.state == 'cancel':
                    continue
                role = move.picking_id.show_loan_role
                if move.state == 'done':
                    qty = move.product_uom._compute_quantity(move.quantity, line.uom_id)
                    if role == 'loan':
                        issued += qty
                    elif role == 'return':
                        returned += qty
                elif role == 'return':
                    pending += move.product_uom._compute_quantity(move.product_uom_qty, line.uom_id)
            line.qty_issued = issued
            line.qty_returned = returned
            line.qty_available = issued - returned - pending

    def write(self, vals):
        if {'loan_id', 'product_id', 'uom_id', 'qty_requested'}.intersection(vals) and any(
                line.loan_id.state != 'draft' for line in self):
            raise UserError(_('A confirmed loan line cannot be edited.'))
        return super().write(vals)

    def unlink(self):
        if any(line.loan_id.state != 'draft' for line in self):
            raise UserError(_('A confirmed loan line cannot be deleted.'))
        return super().unlink()
