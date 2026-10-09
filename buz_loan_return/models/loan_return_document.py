# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class LoanReturnDocument(models.Model):
    _name = 'buz.loan.return.document'
    _description = 'BG/RBG Document Register'
    _order = 'create_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Document Number',
        compute='_compute_name',
        store=True,
        index=True,
    )
    document_kind = fields.Selection(
        [
            ('loan', 'BG / Loan'),
            ('return', 'RBG / Return'),
        ],
        string='Document Type',
        required=True,
        index=True,
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Transfer',
        required=True,
        ondelete='restrict',
        index=True,
    )
    source_document_id = fields.Many2one(
        'buz.loan.return.document',
        string='Source BG',
        domain=[('document_kind', '=', 'loan')],
        ondelete='restrict',
        index=True,
    )
    return_document_ids = fields.One2many(
        'buz.loan.return.document',
        'source_document_id',
        string='Return Documents',
    )
    company_id = fields.Many2one(
        related='picking_id.company_id',
        store=True,
        index=True,
    )
    operation_type_id = fields.Many2one(
        related='picking_id.picking_type_id',
        string='Operation Type',
        store=True,
    )
    partner_id = fields.Many2one(
        related='picking_id.partner_id',
        string='Contact',
        store=True,
    )
    state = fields.Selection(
        related='picking_id.state',
        string='Status',
        store=True,
    )
    scheduled_date = fields.Datetime(
        related='picking_id.scheduled_date',
        string='Scheduled Date',
        store=True,
    )

    _sql_constraints = [
        (
            'picking_unique',
            'unique(picking_id)',
            'A stock transfer can only have one BG/RBG register entry.',
        ),
    ]

    @api.depends('picking_id.name')
    def _compute_name(self):
        for document in self:
            document.name = document.picking_id.name or _('New')

    @api.constrains('document_kind', 'picking_id', 'source_document_id')
    def _check_document_links(self):
        for document in self:
            picking = document.picking_id
            if not picking.partner_id:
                raise ValidationError(_('A contact is required for registered BG/RBG documents.'))
            active_moves = picking.move_ids.filtered(
                lambda move: move.state != 'cancel'
                and move.product_id
                and move.product_uom_qty > 0
            )
            if not active_moves:
                raise ValidationError(_(
                    'Add at least one product line with a quantity greater than zero.'
                ))

            picking.picking_type_id._check_loan_return_operation_type(
                picking.company_id, document.document_kind
            )

            if document.document_kind == 'loan' and document.source_document_id:
                raise ValidationError(_('A BG cannot have a source BG.'))
            if document.document_kind == 'return':
                if not document.source_document_id:
                    raise ValidationError(_('An RBG must be linked to its source BG.'))
                if document.source_document_id.document_kind != 'loan':
                    raise ValidationError(_('An RBG can only be linked to a BG.'))
                if document.source_document_id.company_id != document.picking_id.company_id:
                    raise ValidationError(_('The BG and RBG must belong to the same company.'))
                if document.source_document_id.picking_id == document.picking_id:
                    raise ValidationError(_('A document cannot be its own source BG.'))

    def action_open_picking(self):
        self.ensure_one()
        form_view = self.env.ref('buz_loan_return.view_stock_picking_form_loan_return')
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'views': [(form_view.id, 'form')],
            'res_id': self.picking_id.id,
            'target': 'current',
        }

    def action_create_rbg(self):
        self.ensure_one()
        if self.document_kind != 'loan':
            raise ValidationError(_('RBG can only be created from a BG.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create RBG'),
            'res_model': 'buz.loan.return.create.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_kind': 'return',
                'default_source_document_id': self.id,
                'default_company_id': self.company_id.id,
            },
        }
