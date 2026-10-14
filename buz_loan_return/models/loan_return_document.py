# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class LoanReturnDocument(models.Model):
    _name = 'buz.loan.return.document'
    _description = 'BG/RBG Document Register'
    _order = 'create_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string='Document Number', compute='_compute_name', store=True, index=True)
    document_kind = fields.Selection(
        [('loan', 'BG / Loan'), ('return', 'RBG / Return')],
        string='Document Type', required=True, index=True,
    )
    picking_id = fields.Many2one(
        'stock.picking', string='Stock Transfer', required=True,
        ondelete='restrict', index=True,
    )
    source_document_id = fields.Many2one(
        'buz.loan.return.document', string='Source BG',
        domain=[('document_kind', '=', 'loan')], ondelete='restrict', index=True,
    )
    return_document_ids = fields.One2many(
        'buz.loan.return.document', 'source_document_id', string='Return Documents',
    )
    backorder_picking_ids = fields.One2many(
        'stock.picking', 'loan_return_source_document_id', string='Backorder Transfers',
    )
    company_id = fields.Many2one(related='picking_id.company_id', store=True, index=True)
    operation_type_id = fields.Many2one(
        related='picking_id.picking_type_id', string='Operation Type', store=True,
    )
    partner_id = fields.Many2one(related='picking_id.partner_id', string='Contact', store=True)
    state = fields.Selection(related='picking_id.state', string='Transfer Status', store=True)
    scheduled_date = fields.Datetime(related='picking_id.scheduled_date', string='Scheduled Date', store=True)
    loan_status = fields.Selection(
        [('pending', 'Pending Transfer'), ('active', 'Not Returned'),
         ('partial', 'Partially Returned'), ('returned', 'Returned'),
         ('unlinked', 'Return Items Not Linked'),
         ('cancelled', 'Cancelled Before Transfer')],
        compute='_compute_loan_status', string='Loan Status',
    )

    _sql_constraints = [
        ('picking_unique', 'unique(picking_id)', 'A stock transfer can only have one BG/RBG register entry.'),
    ]

    @api.depends('picking_id.name')
    def _compute_name(self):
        for document in self:
            document.name = document.picking_id.name or _('New')

    @api.depends('document_kind', 'picking_id.state', 'picking_id.move_ids.state',
                 'picking_id.move_ids.quantity', 'picking_id.move_ids.loan_return_return_move_ids.state',
                 'picking_id.move_ids.loan_return_return_move_ids.quantity',
                 'backorder_picking_ids.state', 'backorder_picking_ids.move_ids.state',
                 'backorder_picking_ids.move_ids.quantity', 'return_document_ids.state',
                 'return_document_ids.picking_id.move_ids.state')
    def _compute_loan_status(self):
        loan_documents = self.filtered(lambda item: item.document_kind == 'loan')
        source_moves = loan_documents.mapped('picking_id.move_ids') | loan_documents.mapped('backorder_picking_ids.move_ids')
        source_moves = source_moves.filtered(lambda move: move.state == 'done' and move.product_id)
        returned_by_source = defaultdict(float)
        if source_moves:
            return_moves = self.env['stock.move'].sudo().search([
                ('loan_return_source_move_id', 'in', source_moves.ids),
                ('state', '=', 'done'),
            ])
            for move in return_moves:
                source = move.loan_return_source_move_id
                returned_by_source[source.id] += move.product_uom._compute_quantity(
                    move.quantity, source.product_uom,
                )
        for document in self:
            transfer_set = document.picking_id | document.backorder_picking_ids
            if transfer_set and all(picking.state == 'cancel' for picking in transfer_set):
                document.loan_status = 'cancelled'
                continue
            if any(picking.state not in ('done', 'cancel') for picking in transfer_set):
                document.loan_status = 'pending'
                continue
            if document.document_kind != 'loan':
                document.loan_status = 'pending'
                continue
            moves = (document.picking_id | document.backorder_picking_ids).mapped('move_ids').filtered(
                lambda move: move.state == 'done' and move.product_id
            )
            if not moves:
                document.loan_status = 'cancelled' if transfer_set else 'pending'
                continue
            any_returned = False
            all_returned = True
            for move in moves:
                returned = returned_by_source[move.id]
                any_returned |= float_compare(
                    returned, 0.0, precision_rounding=move.product_uom.rounding,
                ) > 0
                all_returned &= float_compare(
                    returned, move.quantity, precision_rounding=move.product_uom.rounding,
                ) >= 0
            completed_return_moves = document.return_document_ids.filtered(
                lambda item: item.state == 'done'
            ).mapped('picking_id.move_ids')
            completed_return_moves |= document.return_document_ids.filtered(
                lambda item: item.state == 'done'
            ).mapped('backorder_picking_ids.move_ids')
            if any(move.state == 'done' and move.product_id and not move.loan_return_source_move_id for move in completed_return_moves):
                document.loan_status = 'unlinked'
            else:
                document.loan_status = 'returned' if all_returned else 'partial' if any_returned else 'active'
    @api.constrains('document_kind', 'picking_id', 'source_document_id')
    def _check_document_links(self):
        for document in self:
            picking = document.picking_id
            if not picking.partner_id:
                raise ValidationError(_('A contact is required for registered BG/RBG documents.'))
            active_moves = picking.move_ids.filtered(
                lambda move: move.state != 'cancel' and move.product_id and move.product_uom_qty > 0
            )
            if not active_moves:
                raise ValidationError(_('Add at least one product line with a quantity greater than zero.'))
            picking.picking_type_id._check_loan_return_operation_type(
                picking.company_id, document.document_kind,
            )
            if document.document_kind == 'loan' and document.source_document_id:
                raise ValidationError(_('A BG cannot have a source BG.'))
            if document.document_kind == 'return':
                source = document.source_document_id
                if not source or source.document_kind != 'loan':
                    raise ValidationError(_('An RBG must be linked to its source BG.'))
                if source.company_id != picking.company_id:
                    raise ValidationError(_('The BG and RBG must belong to the same company.'))
                if source.partner_id != picking.partner_id:
                    raise ValidationError(_('The BG and RBG must use the same contact.'))
                if source.picking_id == picking:
                    raise ValidationError(_('A document cannot be its own source BG.'))
                for move in active_moves.filtered('loan_return_source_move_id'):
                    source_move = move.loan_return_source_move_id
                    if (source_move.picking_id != source.picking_id and source_move.picking_id not in source.backorder_picking_ids) or source_move.product_id != move.product_id:
                        raise ValidationError(_('Each RBG item must refer to the same product in its source BG.'))

    def _check_loan_return_quantities(self):
        documents = self.filtered(lambda item: item.document_kind == 'return' and item.source_document_id)
        source_ids = sorted(documents.mapped('source_document_id').ids)
        for source_id in source_ids:
            self.env.cr.execute(
                'SELECT id FROM buz_loan_return_document WHERE id = %s FOR UPDATE', [source_id],
            )
        for document in documents.sudo():
            return_pickings = document.picking_id | document.backorder_picking_ids
            for return_move in return_pickings.mapped('move_ids').filtered(
                lambda move: move.state != 'cancel' and move.loan_return_source_move_id
            ):
                source_move = return_move.loan_return_source_move_id
                if source_move.state != 'done' or (source_move.picking_id != document.source_document_id.picking_id and source_move.picking_id not in document.source_document_id.backorder_picking_ids):
                    raise ValidationError(_('Each RBG item must refer to a completed item in its source BG.'))
                reserved = 0.0
                siblings = self.env['stock.move'].sudo().search([
                    ('loan_return_source_move_id', '=', source_move.id),
                    ('state', '!=', 'cancel'),
                ])
                for sibling in siblings:
                    quantity = (sibling.quantity or sibling.product_uom_qty) if sibling.picking_id == document.picking_id else sibling.quantity if sibling.state == 'done' else sibling.product_uom_qty
                    reserved += sibling.product_uom._compute_quantity(quantity, source_move.product_uom)
                if float_compare(
                    reserved, source_move.quantity,
                    precision_rounding=source_move.product_uom.rounding,
                ) > 0:
                    raise ValidationError(_(
                        'The total RBG quantity exceeds the completed quantity for BG item %s.'
                    ) % source_move.product_id.display_name)

    def action_open_picking(self):
        self.ensure_one()
        form_view = self.env.ref('buz_loan_return.view_stock_picking_form_loan_return')
        return {
            'type': 'ir.actions.act_window', 'name': self.name,
            'res_model': 'stock.picking', 'view_mode': 'form',
            'views': [(form_view.id, 'form')], 'res_id': self.picking_id.id,
            'target': 'current',
        }

    def action_create_rbg(self):
        self.ensure_one()
        if self.document_kind != 'loan':
            raise ValidationError(_('RBG can only be created from a BG.'))
        return {
            'type': 'ir.actions.act_window', 'name': _('Create RBG'),
            'res_model': 'buz.loan.return.create.wizard', 'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_kind': 'return',
                'default_source_document_id': self.id,
                'default_company_id': self.company_id.id,
                'default_partner_id': self.partner_id.id,
            },
        }