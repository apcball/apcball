# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, Command
from odoo.exceptions import ValidationError


class CreateLoanReturnWizard(models.TransientModel):
    _name = 'buz.loan.return.create.wizard'
    _description = 'Create BG/RBG Stock Transfer'

    document_kind = fields.Selection(
        [
            ('loan', 'BG / Loan'),
            ('return', 'RBG / Return'),
        ],
        required=True,
        default=lambda self: self.env.context.get('default_document_kind', 'loan'),
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    operation_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operation Type',
        required=True,
        domain=[('code', '=', 'internal')],
    )
    allowed_operation_type_ids = fields.Many2many(
        'stock.picking.type',
        compute='_compute_allowed_operation_types',
    )
    source_document_id = fields.Many2one(
        'buz.loan.return.document',
        string='Source BG',
        domain=[('document_kind', '=', 'loan')],
        readonly=True,
    )

    @api.depends('document_kind', 'company_id')
    def _compute_allowed_operation_types(self):
        config_model = self.env['buz.loan.return.operation.type']
        for wizard in self:
            configs = config_model.search([
                ('company_id', '=', wizard.company_id.id),
                ('document_kind', '=', wizard.document_kind),
            ]) if wizard.company_id and wizard.document_kind else config_model
            wizard.allowed_operation_type_ids = configs.mapped('picking_type_id')

    @api.onchange('document_kind', 'company_id')
    def _onchange_operation_type_domain(self):
        return {
            'domain': {
                'operation_type_id': [
                    ('id', 'in', self.allowed_operation_type_ids.ids),
                ],
            },
        }

    def action_open_picking(self):
        self.ensure_one()
        config = self.env['buz.loan.return.operation.type'].search([
            ('company_id', '=', self.company_id.id),
            ('document_kind', '=', self.document_kind),
            ('picking_type_id', '=', self.operation_type_id.id),
        ], limit=1)
        if not config:
            raise ValidationError(_(
                'The selected Operation Type is not configured for this document type.'
            ))

        context = {
            'default_picking_type_id': self.operation_type_id.id,
            'default_company_id': self.company_id.id,
            'default_location_id': self.operation_type_id.default_location_src_id.id,
            'default_location_dest_id': self.operation_type_id.default_location_dest_id.id,
            'loan_return_document_kind': self.document_kind,
        }
        if self.document_kind == 'return':
            source_document = self.source_document_id
            if not source_document or source_document.document_kind != 'loan':
                raise ValidationError(_('Select a valid source BG to create an RBG.'))
            if source_document.company_id != self.company_id:
                raise ValidationError(_('BG and RBG must belong to the same company.'))
            context.update({
                'loan_return_source_document_id': source_document.id,
                'default_partner_id': source_document.picking_id.partner_id.id,
                'default_origin': source_document.picking_id.name,
                'default_move_ids_without_package': [
                    Command.create({
                        'name': move.description_picking or move.name,
                        'product_id': move.product_id.id,
                        'product_uom': move.product_uom.id,
                        'product_uom_qty': move.product_uom_qty,
                        'location_id': self.operation_type_id.default_location_src_id.id,
                        'location_dest_id': self.operation_type_id.default_location_dest_id.id,
                    })
                    for move in source_document.picking_id.move_ids
                    if move.state != 'cancel' and move.product_id
                ],
            })

        form_view = self.env.ref('buz_loan_return.view_stock_picking_form_loan_return')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create BG') if self.document_kind == 'loan' else _('Create RBG'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'views': [(form_view.id, 'form')],
            'target': 'current',
            'context': context,
        }