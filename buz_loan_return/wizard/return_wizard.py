# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class ReturnWizard(models.TransientModel):
    _name = 'buz.loan.return.return.wizard'
    _description = 'Create Show Return'

    source_picking_id = fields.Many2one(
        'stock.picking', required=True, readonly=True, string='Source Loan Document',
    )
    company_id = fields.Many2one(
        'res.company', related='source_picking_id.company_id', readonly=True,
    )
    operation_type_id = fields.Many2one(
        'stock.picking.type', required=True, string='Return Operation Type',
        domain="[('code', '=', 'internal'), ('active', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    scheduled_date = fields.Datetime(
        required=True, default=fields.Datetime.now, string='Scheduled Date',
    )
    location_id = fields.Many2one(
        'stock.location', required=True, string='Return From', readonly=True,
    )
    location_dest_id = fields.Many2one(
        'stock.location', required=True, string='Return To', readonly=True,
    )
    line_ids = fields.One2many(
        'buz.loan.return.return.wizard.line', 'wizard_id', string='Products to Return',
    )

    @staticmethod
    def _sequence_markers(operation_type):
        return ' '.join((
            operation_type.sequence_code or '',
            operation_type.sequence_id.prefix or '',
        )).upper()

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        source_id = values.get('source_picking_id') or self.env.context.get('default_source_picking_id')
        source = self.env['stock.picking'].browse(source_id).exists()
        if not source:
            return values
        source = source.loan_return_root_id or source
        values.update({
            'source_picking_id': source.id,
            'location_id': source.location_dest_id.id,
        })
        company = source.company_id
        candidates = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'), ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ])
        candidates = candidates.filtered(
            lambda item: 'RBG' in self._sequence_markers(item)
        )
        candidates = candidates.sorted(
            key=lambda item: (item.company_id != company, item.sequence, item.id)
        )
        if candidates:
            operation_type = candidates[0]
            values['operation_type_id'] = operation_type.id
            values['location_dest_id'] = operation_type.default_location_dest_id.id
        if 'line_ids' in fields_list:
            line_commands = []
            for product_id, balance in source._get_loan_return_balances().items():
                remaining = balance['remaining']
                product = self.env['product.product'].browse(product_id)
                if float_compare(remaining, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
                    continue
                line_commands.append(Command.create({
                    'product_id': product_id,
                    'delivered_qty': balance['delivered'],
                    'reserved_qty': balance['reserved'],
                    'remaining_qty': remaining,
                    'quantity': remaining,
                }))
            values['line_ids'] = line_commands
        return values

    @api.onchange('operation_type_id')
    def _onchange_operation_type(self):
        if self.operation_type_id:
            self.location_dest_id = self.operation_type_id.default_location_dest_id

    def action_create_return(self):
        self.ensure_one()
        source = self.source_picking_id.loan_return_root_id or self.source_picking_id
        if source.loan_return_role != 'loan' or source.state != 'done':
            raise ValidationError(_('The source loan must be completed before a return can be created.'))
        operation_type = self.operation_type_id
        if not operation_type or not operation_type.active or operation_type.code != 'internal':
            raise ValidationError(_('Select an active Internal Transfer Operation Type for the return.'))
        if 'RBG' not in self._sequence_markers(operation_type):
            raise ValidationError(_('Select the RBG Operation Type for a show return.'))
        if operation_type.company_id and operation_type.company_id != source.company_id:
            raise ValidationError(_('The Return Operation Type must belong to the source loan company.'))
        if not self.location_id or not self.location_dest_id:
            raise UserError(_('Select valid return locations.'))
        if not self.line_ids:
            raise UserError(_('There are no remaining product quantities to return.'))

        current_balances = source._get_loan_return_balances()
        requested = {}
        for line in self.line_ids:
            if line.quantity <= 0:
                raise ValidationError(_('Return quantities must be greater than zero.'))
            requested[line.product_id.id] = requested.get(line.product_id.id, 0.0) + line.quantity
        for product_id, quantity in requested.items():
            product = self.env['product.product'].browse(product_id)
            available = current_balances.get(product_id, {}).get('remaining', 0.0)
            if float_compare(
                quantity, available, precision_rounding=product.uom_id.rounding,
            ) > 0:
                raise ValidationError(_(
                    'The requested return quantity for %(product)s exceeds the remaining quantity of %(remaining)s.',
                    product=product.display_name,
                    remaining=available,
                ))

        move_values = [
            Command.create({
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.quantity,
                'location_id': self.location_id.id,
                'location_dest_id': self.location_dest_id.id,
            })
            for line in self.line_ids
        ]
        picking = self.env['stock.picking'].create({
            'loan_return_role': 'return',
            'loan_return_type': source.loan_return_type,
            'loan_return_source_id': source.id,
            'picking_type_id': operation_type.id,
            'partner_id': source.partner_id.id,
            'origin': source.name,
            'scheduled_date': self.scheduled_date,
            'location_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
            'move_ids': move_values,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': picking.display_name,
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': picking.id,
            'target': 'current',
        }


class ReturnWizardLine(models.TransientModel):
    _name = 'buz.loan.return.return.wizard.line'
    _description = 'Show Return Product'

    wizard_id = fields.Many2one(
        'buz.loan.return.return.wizard', required=True, ondelete='cascade',
    )
    product_id = fields.Many2one('product.product', required=True, readonly=True)
    delivered_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    reserved_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    remaining_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    quantity = fields.Float(required=True, digits='Product Unit of Measure')
