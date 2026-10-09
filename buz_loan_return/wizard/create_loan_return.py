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
        for wizard in self:
            if not wizard.company_id:
                wizard.allowed_operation_type_ids = False
                continue

            # รวมประเภทที่ใช้ร่วมกัน (ไม่มีบริษัทกำกับ) และประเภทของบริษัทที่เลือก
            domain = [
                ('code', '=', 'internal'),
                '|',
                ('company_id', '=', False),
                ('company_id', '=', wizard.company_id.id),
            ]
            if wizard.document_kind == 'loan':
                domain += [
                    ('reservation_method', '=', 'at_confirm'),
                    ('default_location_src_id', '!=', False),
                ]

            wizard.allowed_operation_type_ids = self.env['stock.picking.type'].search(domain)

    @api.onchange('document_kind', 'company_id')
    def _onchange_operation_type_domain(self):
        if self.operation_type_id not in self.allowed_operation_type_ids:
            self.operation_type_id = False
        return {
            'domain': {
                'operation_type_id': [
                    ('id', 'in', self.allowed_operation_type_ids.ids),
                ],
            },
        }

    def action_open_picking(self):
        self.ensure_one()
        if self.operation_type_id not in self.allowed_operation_type_ids:
            raise ValidationError(_(
                'Select an Internal Transfer Operation Type available for this company and document type.'
            ))
        self.operation_type_id._check_loan_return_operation_type(
            self.company_id, self.document_kind
        )

        destination = (
            self._get_default_loan_destination(self.company_id)
            if self.document_kind == 'loan' else False
        )
        context = {
            'default_picking_type_id': self.operation_type_id.id,
            'default_company_id': self.company_id.id,
            'default_location_id': self.operation_type_id.default_location_src_id.id,
            'default_location_dest_id': (
                destination.id if self.document_kind == 'loan' and destination
                else self.operation_type_id.default_location_dest_id.id
                if self.document_kind == 'return'
                else False
            ),
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

    def _get_default_loan_destination(self, company):
        """Find the default destination, preferring the current company."""
        location_model = self.env['stock.location']
        location_name = 'FG30/DS-OLT-\u0e25\u0e33\u0e25\u0e39\u0e01\u0e01\u0e32'
        for company_id in (company.id, False):
            locations = location_model.search([
                ('complete_name', '=', location_name),
                ('company_id', '=', company_id),
            ], limit=2)
            if locations:
                return locations[0] if len(locations) == 1 else location_model
        return location_model
