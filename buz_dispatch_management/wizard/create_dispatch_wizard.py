from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BuzCreateDispatchWizard(models.TransientModel):
    _name = 'buz.create.dispatch.wizard'
    _description = 'Create Dispatch Wizard'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery Order',
        required=True,
        readonly=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        readonly=True,
    )

    sale_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        readonly=True,
    )

    dispatch_date = fields.Date(
        string='Dispatch Date',
        required=True,
        default=lambda self: fields.Date.today(),
    )

    driver_name = fields.Char(string='Driver Name')
    vehicle_no = fields.Char(string='Vehicle No.')

    line_ids = fields.One2many(
        'buz.create.dispatch.wizard.line',
        'wizard_id',
        string='Products',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking_id = self._context.get('default_picking_id') or self._context.get('picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            res['picking_id'] = picking.id
            res['partner_id'] = picking.partner_id.id
            res['sale_id'] = picking.sale_id.id

            remaining_map = {}
            existing_dispatches = self.env['buz.dispatch.document'].search([
                ('picking_id', '=', picking.id),
                ('state', '!=', 'cancel'),
            ])
            for line in existing_dispatches.line_ids:
                key = (line.product_id.id, line.sale_line_id.id)
                remaining_map[key] = remaining_map.get(key, 0.0) + line.dispatch_qty

            lines = []
            for move in picking.move_ids.filtered(lambda m: m.product_uom_qty > 0):
                dispatched = remaining_map.get((move.product_id.id, move.sale_line_id.id), 0.0)
                remaining = move.product_uom_qty - dispatched
                if remaining > 0.0:
                    lines.append((0, 0, {
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'ordered_qty': move.product_uom_qty,
                        'dispatch_qty': remaining,
                        'sale_line_id': move.sale_line_id.id,
                        'move_line_id': move.move_line_ids[:1].id if move.move_line_ids else False,
                    }))
            res['line_ids'] = lines
        return res

    def action_create_dispatch(self):
        self.ensure_one()

        if not self.line_ids:
            raise UserError(_('At least one product line is required.'))

        picking = self.picking_id
        if picking.state == 'cancel':
            raise UserError(_('Cannot create dispatch for a cancelled delivery order.'))

        for line in self.line_ids:
            if line.dispatch_qty <= 0:
                raise UserError(
                    _('Dispatch quantity must be greater than 0 for %s.')
                    % line.product_id.display_name
                )
            if line.ordered_qty and line.dispatch_qty > line.ordered_qty:
                raise UserError(
                    _('Dispatch quantity for %s cannot exceed ordered quantity (%s).')
                    % (line.product_id.display_name, line.ordered_qty)
                )

        remaining_map = {}
        existing_dispatches = self.env['buz.dispatch.document'].search([
            ('picking_id', '=', picking.id),
            ('state', '!=', 'cancel'),
        ])
        for existing_line in existing_dispatches.line_ids:
            key = (existing_line.product_id.id, existing_line.sale_line_id.id)
            remaining_map[key] = remaining_map.get(key, 0.0) + existing_line.dispatch_qty

        for line in self.line_ids:
            key = (line.product_id.id, line.sale_line_id.id)
            prev_dispatched = remaining_map.get(key, 0.0)
            if line.ordered_qty and prev_dispatched + line.dispatch_qty > line.ordered_qty:
                raise UserError(
                    _('Over-dispatch prevented for %s. Already dispatched %s of %s, cannot dispatch %s more.')
                    % (line.product_id.display_name, prev_dispatched, line.ordered_qty, line.dispatch_qty)
                )

        doc = self.env['buz.dispatch.document'].with_context(mail_create_nosubscribe=True).create({
            'picking_id': picking.id,
            'partner_id': self.partner_id.id,
            'sale_id': self.sale_id.id,
            'dispatch_date': self.dispatch_date,
            'driver_name': self.driver_name,
            'vehicle_no': self.vehicle_no,
            'line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_id': line.product_uom_id.id,
                'ordered_qty': line.ordered_qty,
                'dispatch_qty': line.dispatch_qty,
                'sale_line_id': line.sale_line_id.id,
                'move_line_id': line.move_line_id or False,
            }) for line in self.line_ids],
        })

        return {
            'name': _('Dispatch Document'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.dispatch.document',
            'res_id': doc.id,
            'view_mode': 'form',
            'target': 'current',
        }


class BuzCreateDispatchWizardLine(models.TransientModel):
    _name = 'buz.create.dispatch.wizard.line'
    _description = 'Create Dispatch Wizard Line'

    wizard_id = fields.Many2one(
        'buz.create.dispatch.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
    )

    product_uom_id = fields.Many2one(
        'uom.uom',
        string='UoM',
    )

    ordered_qty = fields.Float(
        string='Ordered Qty',
        digits='Product Unit of Measure',
        readonly=True,
    )

    dispatch_qty = fields.Float(
        string='Dispatch Qty',
        digits='Product Unit of Measure',
        required=True,
    )

    sale_line_id = fields.Many2one(
        'sale.order.line',
        string='Sale Order Line',
    )

    move_line_id = fields.Integer(string='Stock Move Line ID')
