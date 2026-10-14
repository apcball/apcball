# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, Command
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class CreateLoanReturnWizard(models.TransientModel):
    _name = 'buz.loan.return.create.wizard'
    _description = 'Create BG/RBG Document'

    document_kind = fields.Selection(
        [('loan', 'BG / Loan'), ('return', 'RBG / Return')],
        required=True,
        default=lambda self: self.env.context.get('default_document_kind', 'loan'),
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    operation_type_id = fields.Many2one(
        'stock.picking.type', string='Operation Type', required=True,
        domain="[('code', '=', 'internal'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    partner_id = fields.Many2one('res.partner', string='Contact', required=True)
    source_document_id = fields.Many2one(
        'buz.loan.return.document', string='Source BG', readonly=True,
        domain=[('document_kind', '=', 'loan')],
    )
    scheduled_date = fields.Datetime(default=fields.Datetime.now)
    location_id = fields.Many2one('stock.location', string='Source Location')
    location_dest_id = fields.Many2one('stock.location', string='Destination Location')
    line_ids = fields.One2many(
        'buz.loan.return.create.wizard.line', 'wizard_id', string='Products',
    )
    created_document_id = fields.Many2one(
        'buz.loan.return.document', readonly=True, ondelete='set null',
    )
    allowed_operation_type_ids = fields.Many2many(
        'stock.picking.type', compute='_compute_allowed_operation_types',
    )
    operation_type_message = fields.Char(
        string='Operation Type Availability',
        compute='_compute_allowed_operation_types',
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if values.get('document_kind') != 'return' or not values.get('source_document_id'):
            return values
        source = self.env['buz.loan.return.document'].browse(values['source_document_id']).exists()
        if not source or source.document_kind != 'loan':
            return values
        values.update({
            'partner_id': source.partner_id.id,
            'location_id': source.picking_id.location_dest_id.id,
            'location_dest_id': source.picking_id.location_id.id,
        })
        lines = []
        pickings = source.picking_id | source.backorder_picking_ids
        for move in pickings.mapped('move_ids').filtered(
            lambda item: item.state == 'done' and item.product_id
        ):
            remaining = self._remaining_for_source_move(move)
            if float_compare(remaining, 0, precision_rounding=move.product_uom.rounding) > 0:
                lines.append(Command.create({
                    'source_move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': remaining,
                }))
        values['line_ids'] = lines
        return values
    @api.depends('document_kind', 'company_id')
    def _compute_allowed_operation_types(self):
        for wizard in self:
            operation_types = wizard._get_eligible_operation_types()
            wizard.allowed_operation_type_ids = operation_types
            if operation_types or not wizard.company_id:
                wizard.operation_type_message = False
            elif wizard.document_kind == 'loan':
                wizard.operation_type_message = _(
                    'No eligible Internal Transfer Operation Type is available. '
                    'BG requires an active type with At Confirmation reservation '
                    'and a default Source Location for this company.'
                )
            else:
                wizard.operation_type_message = _(
                    'No active Internal Transfer Operation Type is available '
                    'for this company.'
                )

    def _get_eligible_operation_types(self):
        """Return operation types that this BG/RBG wizard may use."""
        self.ensure_one()
        if not self.company_id or self.document_kind not in ('loan', 'return'):
            return self.env['stock.picking.type']

        domain = [
            ('active', '=', True),
            ('code', '=', 'internal'),
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
        ]
        if self.document_kind == 'loan':
            domain += [
                ('reservation_method', '=', 'at_confirm'),
                ('default_location_src_id', '!=', False),
            ]
        return self.env['stock.picking.type'].search(domain)

    @api.onchange('document_kind', 'company_id')
    def _onchange_operation_type_domain(self):
        if self.operation_type_id not in self.allowed_operation_type_ids:
            self.operation_type_id = False
        return {'domain': {'operation_type_id': [('id', 'in', self.allowed_operation_type_ids.ids)]}}

    @api.onchange('operation_type_id', 'document_kind')
    def _onchange_locations(self):
        if not self.operation_type_id:
            return
        if self.document_kind == 'loan':
            self.location_id = self.operation_type_id.default_location_src_id
            self.location_dest_id = self._get_default_loan_destination(self.company_id)
        else:
            source = self.source_document_id.picking_id if self.source_document_id else False
            self.location_id = source.location_dest_id if source else self.operation_type_id.default_location_src_id
            self.location_dest_id = source.location_id if source else self.operation_type_id.default_location_dest_id

    @api.onchange('source_document_id')
    def _onchange_source_document(self):
        if not self.source_document_id:
            return
        picking = self.source_document_id.picking_id
        self.partner_id = picking.partner_id
        self.location_id = picking.location_dest_id
        self.location_dest_id = picking.location_id
        self.line_ids = [Command.clear()]
        lines = []
        source_pickings = picking | self.source_document_id.backorder_picking_ids
        for move in source_pickings.mapped('move_ids').filtered(lambda item: item.state == 'done' and item.product_id):
            remaining = self._remaining_for_source_move(move)
            if float_compare(remaining, 0, precision_rounding=move.product_uom.rounding) > 0:
                lines.append(Command.create({
                    'source_move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': remaining,
                }))
        self.line_ids = lines

    def _remaining_for_source_move(self, source_move):
        returned = 0.0
        return_moves = self.env['stock.move'].sudo().search([
            ('loan_return_source_move_id', '=', source_move.id),
            ('state', '!=', 'cancel'),
        ])
        for move in return_moves:
            quantity = move.quantity if move.state == 'done' else move.product_uom_qty
            returned += move.product_uom._compute_quantity(quantity, source_move.product_uom)
        return source_move.quantity - returned

    def action_create_document(self):
        self.ensure_one()
        self.env.cr.execute(
            'SELECT id FROM buz_loan_return_create_wizard WHERE id = %s FOR UPDATE',
            [self.id],
        )
        self.invalidate_recordset(['created_document_id'])
        if self.created_document_id:
            return self._action_open_document(self.created_document_id)
        if self.operation_type_id not in self._get_eligible_operation_types():
            raise ValidationError(_('Select an eligible Internal Transfer Operation Type.'))
        self.operation_type_id._check_loan_return_operation_type(self.company_id, self.document_kind)
        if not self.partner_id or not self.line_ids:
            raise ValidationError(_('Enter a contact and at least one product line.'))
        if self.document_kind == 'return' and self.source_document_id:
            self.env.cr.execute(
                'SELECT id FROM buz_loan_return_document WHERE id = %s FOR UPDATE',
                [self.source_document_id.id],
            )
        location_id = self.location_id or self.operation_type_id.default_location_src_id
        location_dest_id = self.location_dest_id or self.operation_type_id.default_location_dest_id
        if self.document_kind == 'loan' and not self.location_dest_id:
            location_dest_id = self._get_default_loan_destination(self.company_id) or location_dest_id
        if not location_id or not location_dest_id:
            raise ValidationError(_('Select valid source and destination locations.'))
        if self.document_kind == 'return':
            if not self.source_document_id or self.source_document_id.document_kind != 'loan':
                raise ValidationError(_('Select a valid source BG.'))
            if self.source_document_id.company_id != self.company_id:
                raise ValidationError(_('The BG and RBG must belong to the same company.'))
            if self.partner_id != self.source_document_id.partner_id:
                raise ValidationError(_('The RBG contact must match its source BG.'))

        move_values = []
        for line in self.line_ids:
            if line.quantity <= 0:
                raise ValidationError(_('Each product quantity must be greater than zero.'))
            values = {
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom': line.product_uom_id.id,
                'product_uom_qty': line.quantity,
                'location_id': location_id.id,
                'location_dest_id': location_dest_id.id,
            }
            if self.document_kind == 'return':
                source_move = line.source_move_id
                if not source_move or (source_move.picking_id != self.source_document_id.picking_id and source_move.picking_id not in self.source_document_id.backorder_picking_ids):
                    raise ValidationError(_('Each RBG line must reference an item in the selected BG.'))
                if source_move.product_id != line.product_id:
                    raise ValidationError(_('The RBG product must match the source BG item.'))
                remaining = self._remaining_for_source_move(source_move)
                requested = line.product_uom_id._compute_quantity(line.quantity, source_move.product_uom)
                if float_compare(requested, remaining, precision_rounding=source_move.product_uom.rounding) > 0:
                    raise ValidationError(_('The RBG quantity exceeds the remaining BG quantity.'))
                values['loan_return_source_move_id'] = source_move.id
            move_values.append(Command.create(values))

        context = {
            'loan_return_document_kind': self.document_kind,
            'loan_return_source_document_id': self.source_document_id.id if self.source_document_id else False,
        }
        picking = self.env['stock.picking'].with_context(**context).create({
            'picking_type_id': self.operation_type_id.id,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'scheduled_date': self.scheduled_date,
            'location_id': location_id.id,
            'location_dest_id': location_dest_id.id,
            'origin': self.source_document_id.name if self.source_document_id else False,
            'move_ids': move_values,
        })
        document = self.env['buz.loan.return.document'].search(
            [('picking_id', '=', picking.id)], limit=1,
        )
        if not document:
            raise ValidationError(_('The BG/RBG register entry could not be created.'))
        self.created_document_id = document.id
        return self._action_open_document(document)

    @staticmethod
    def _action_open_document(document):
        return {
            'type': 'ir.actions.act_window',
            'name': document.name,
            'res_model': 'buz.loan.return.document',
            'view_mode': 'form',
            'res_id': document.id,
            'target': 'current',
        }

    @api.model
    def _get_default_loan_destination(self, company):
        location_model = self.env['stock.location']
        location_name = 'FG30/DS-OLT-\u0e25\u0e33\u0e25\u0e39\u0e01\u0e01\u0e32'
        for company_id in (company.id, False):
            locations = location_model.search([
                ('complete_name', '=', location_name), ('company_id', '=', company_id),
            ], limit=2)
            if len(locations) == 1:
                return locations
            if locations:
                return location_model
        return location_model


class CreateLoanReturnWizardLine(models.TransientModel):
    _name = 'buz.loan.return.create.wizard.line'
    _description = 'BG/RBG Product Line'

    wizard_id = fields.Many2one('buz.loan.return.create.wizard', required=True, ondelete='cascade')
    source_move_id = fields.Many2one('stock.move', string='BG Item', readonly=True)
    product_id = fields.Many2one('product.product', required=True)
    product_uom_category_id = fields.Many2one(
        related='product_id.uom_id.category_id', string='Category',
    )
    product_uom_id = fields.Many2one('uom.uom', string='Unit', required=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
    quantity = fields.Float(required=True, digits='Product Unit of Measure')