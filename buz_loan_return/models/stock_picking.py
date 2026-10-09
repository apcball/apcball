# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    loan_return_document_kind = fields.Selection(
        [
            ('loan', 'BG / Loan'),
            ('return', 'RBG / Return'),
        ],
        string='BG/RBG Type',
        compute='_compute_loan_return_register',
        compute_sudo=True,
    )
    loan_return_source_picking_id = fields.Many2one(
        'stock.picking',
        string='Source BG',
        compute='_compute_loan_return_register',
        compute_sudo=True,
    )

    @api.depends('name')
    def _compute_loan_return_register(self):
        registrations = self.env['buz.loan.return.document'].sudo().search([
            ('picking_id', 'in', self.ids),
        ])
        by_picking = {item.picking_id.id: item for item in registrations}
        for picking in self:
            document = by_picking.get(picking.id)
            picking.loan_return_document_kind = document.document_kind if document else False
            picking.loan_return_source_picking_id = (
                document.source_document_id.picking_id
                if document and document.source_document_id
                else False
            )

    @api.model_create_multi
    def create(self, vals_list):
        document_kind = self.env.context.get('loan_return_document_kind')
        if document_kind not in ('loan', 'return'):
            return super().create(vals_list)

        source_document_id = self.env.context.get('loan_return_source_document_id')
        pickings = super().create(vals_list)
        register_model = self.env['buz.loan.return.document'].sudo()
        source_document = register_model.browse(source_document_id).exists()

        for picking in pickings:
            config = self.env['buz.loan.return.operation.type'].sudo().search([
                ('company_id', '=', picking.company_id.id),
                ('document_kind', '=', document_kind),
                ('picking_type_id', '=', picking.picking_type_id.id),
            ], limit=1)
            if not config:
                raise ValidationError(_(
                    'The selected Operation Type is not enabled for this workflow.'
                ))
            if document_kind == 'return':
                if not source_document or source_document.document_kind != 'loan':
                    raise ValidationError(_('RBG must be created from a registered BG.'))
                if source_document.company_id != picking.company_id:
                    raise ValidationError(_('BG and RBG must belong to the same company.'))

            register_values = {
                'document_kind': document_kind,
                'picking_id': picking.id,
            }
            if document_kind == 'return':
                register_values['source_document_id'] = source_document.id
            register_model.create(register_values)
        return pickings

    def _check_loan_return_documents(self):
        documents = self.env['buz.loan.return.document'].sudo().search([
            ('picking_id', 'in', self.ids),
        ])
        for document in documents:
            document._check_document_links()

    def action_confirm(self):
        self._check_loan_return_documents()
        return super().action_confirm()

    def button_validate(self):
        self._check_loan_return_documents()
        return super().button_validate()