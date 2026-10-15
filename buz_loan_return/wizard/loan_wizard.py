# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError


class LoanWizard(models.TransientModel):
    _name = 'buz.loan.return.loan.wizard'
    _description = 'Create Show Loan'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    operation_type_id = fields.Many2one(
        'stock.picking.type', required=True, string='Operation Type',
        domain="[('code', '=', 'internal'), ('active', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    partner_id = fields.Many2one('res.partner', required=True, string='Contact')
    scheduled_date = fields.Datetime(
        required=True, default=fields.Datetime.now, string='Scheduled Date',
    )
    location_id = fields.Many2one(
        'stock.location', required=True, string='Source Location',
        domain="[('usage', '!=', 'view'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    location_dest_id = fields.Many2one(
        'stock.location', required=True, string='Show Location',
        domain="[('usage', '!=', 'view'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    origin = fields.Char(string='Source Document')
    tag_ids = fields.Many2many('buz.picking.tag', string='Tags')
    line_ids = fields.One2many(
        'buz.loan.return.loan.wizard.line', 'wizard_id', string='Products',
    )

    @staticmethod
    def _sequence_markers(operation_type):
        return ' '.join((
            operation_type.sequence_code or '',
            operation_type.sequence_id.prefix or '',
        )).upper()

    @api.onchange('company_id')
    def _onchange_operation_type_domain(self):
        domain = [
            ('code', '=', 'internal'), ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id or False),
        ]
        types = self.env['stock.picking.type'].search(domain)
        loan_types = types.filtered(lambda item: any(
            marker in self._sequence_markers(item)
            for marker in ('BG-RT', 'BG-PJ', 'BG-OL')
        ))
        domain = [('id', 'in', loan_types.ids)]
        if self.operation_type_id not in loan_types:
            self.operation_type_id = False
        if self.operation_type_id:
            self.location_id = self.operation_type_id.default_location_src_id
            self.location_dest_id = self.operation_type_id.default_location_dest_id
        return {'domain': {'operation_type_id': domain}}

    @api.onchange('operation_type_id')
    def _onchange_operation_type(self):
        if self.operation_type_id:
            self.location_id = self.operation_type_id.default_location_src_id
            self.location_dest_id = self.operation_type_id.default_location_dest_id

    @classmethod
    def _loan_type_from_operation_type(cls, operation_type):
        markers = cls._sequence_markers(operation_type)
        matches = [
            loan_type for loan_type in ('rt', 'pj', 'ol')
            if 'BG-' + loan_type.upper() in markers
        ]
        if len(matches) != 1:
            raise ValidationError(_(
                'The Operation Type sequence must identify exactly one loan type: RT, PJ, or OL.'
            ))
        return matches[0]

    def action_create_loan(self):
        self.ensure_one()
        operation_type = self.operation_type_id
        if not operation_type.active or operation_type.code != 'internal':
            raise ValidationError(_('Select an active Internal Transfer Operation Type.'))
        loan_type = self._loan_type_from_operation_type(operation_type)
        if operation_type.company_id and operation_type.company_id != self.company_id:
            raise ValidationError(_('The Operation Type must belong to the selected company.'))
        if not self.line_ids:
            raise UserError(_('Add at least one product to the loan.'))
        if not self.location_id or not self.location_dest_id:
            raise UserError(_('Select valid source and show locations.'))

        move_values = []
        for line in self.line_ids:
            if line.quantity <= 0:
                raise ValidationError(_('Loan quantities must be greater than zero.'))
            if line.product_id.type == 'service':
                raise ValidationError(_('Service products cannot be loaned through inventory transfers.'))
            move_values.append(Command.create({
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.quantity,
                'location_id': self.location_id.id,
                'location_dest_id': self.location_dest_id.id,
            }))

        picking = self.env['stock.picking'].create({
            'loan_return_role': 'loan',
            'loan_return_type': loan_type,
            'picking_type_id': operation_type.id,
            'partner_id': self.partner_id.id,
            'scheduled_date': self.scheduled_date,
            'location_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
            'origin': self.origin or False,
            'tag_ids': [Command.set(self.tag_ids.ids)],
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


class LoanWizardLine(models.TransientModel):
    _name = 'buz.loan.return.loan.wizard.line'
    _description = 'Show Loan Product'

    wizard_id = fields.Many2one(
        'buz.loan.return.loan.wizard', required=True, ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product', required=True,
        domain="[('type', '!=', 'service'), '|', ('company_id', '=', False), ('company_id', '=', parent.company_id)]",
    )
    quantity = fields.Float(required=True, default=1.0, digits='Product Unit of Measure')
