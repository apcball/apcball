# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    def _check_loan_return_operation_type(self, company, document_kind):
        self.ensure_one()
        if document_kind not in ('loan', 'return'):
            raise ValidationError(_('Invalid BG/RBG document type.'))
        if self.code != 'internal':
            raise ValidationError(_('BG/RBG requires an Internal Transfer Operation Type.'))
        if self.company_id and self.company_id != company:
            raise ValidationError(_('The Operation Type must belong to the selected company.'))
        if document_kind == 'loan':
            if self.reservation_method != 'at_confirm':
                raise ValidationError(_('The BG Operation Type must reserve at confirmation.'))
            if not self.default_location_src_id:
                raise ValidationError(_('The BG Operation Type must have a default Source Location.'))


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
    @api.depends_context('loan_return_document_kind')
    def _compute_loan_return_register(self):
        persisted_ids = [picking.id for picking in self if isinstance(picking.id, int)]
        registrations = self.env['buz.loan.return.document'].sudo().search([
            ('picking_id', 'in', persisted_ids),
        ]) if persisted_ids else self.env['buz.loan.return.document']
        by_picking = {item.picking_id.id: item for item in registrations}
        context_kind = self.env.context.get('loan_return_document_kind')
        for picking in self:
            document = by_picking.get(picking.id)
            is_new = not picking._origin or not picking._origin.id
            picking.loan_return_document_kind = (
                document.document_kind if document
                else context_kind if is_new and context_kind in ('loan', 'return')
                else False
            )
            picking.loan_return_source_picking_id = (
                document.source_document_id.picking_id
                if document and document.source_document_id
                else False
            )

    @api.depends('picking_type_id', 'partner_id')
    def _compute_location_id(self):
        # Keep the BG destination chosen in the wizard or by the user.
        # The base compute otherwise resets it to the operation type default.
        previous_destinations = {
            picking.id: picking.location_dest_id for picking in self
        }
        super()._compute_location_id()
        if (
            self.env.context.get('loan_return_document_kind') != 'loan'
            or 'default_location_dest_id' not in self.env.context
        ):
            return
        default_destination_id = self.env.context.get('default_location_dest_id')
        for picking in self:
            if picking.state != 'draft':
                continue
            previous_destination = previous_destinations.get(picking.id)
            if previous_destination:
                picking.location_dest_id = previous_destination
            else:
                picking.location_dest_id = default_destination_id or False
    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if (
            self.env.context.get('loan_return_document_kind') == 'loan'
            and 'location_dest_id' in fields_list
            and 'default_location_dest_id' in self.env.context
            and not self.env.context.get('default_location_dest_id')
        ):
            # ถ้าไม่พบ Location ตั้งต้น อย่าใช้ค่า default ของ Operation Type แทน
            values['location_dest_id'] = False
        return values

    @api.model_create_multi
    def create(self, vals_list):
        document_kind = self.env.context.get('loan_return_document_kind')
        if document_kind not in ('loan', 'return'):
            return super().create(vals_list)

        # ตรวจจากค่าที่ส่งมาจริงก่อนสร้าง picking เพื่อไม่ให้ข้าม domain ของหน้าจอได้
        picking_type_model = self.env['stock.picking.type']
        company_model = self.env['res.company']
        for vals in vals_list:
            picking_type_id = vals.get('picking_type_id') or self.env.context.get(
                'default_picking_type_id'
            )
            company_id = vals.get('company_id') or self.env.context.get(
                'default_company_id'
            ) or self.env.company.id
            if not picking_type_id or not company_id:
                raise ValidationError(_('Select a valid company and Operation Type.'))
            picking_type = picking_type_model.browse(picking_type_id).exists()
            company = company_model.browse(company_id).exists()
            if not picking_type or not company:
                raise ValidationError(_('Select a valid company and Operation Type.'))
            picking_type._check_loan_return_operation_type(company, document_kind)

        source_document_id = self.env.context.get('loan_return_source_document_id')
        pickings = super().create(vals_list)
        register_model = self.env['buz.loan.return.document'].sudo()
        source_document = register_model.browse(source_document_id).exists()

        for picking in pickings:
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

    def _check_loan_return_locations(self):
        documents = self.env['buz.loan.return.document'].sudo().search([
            ('picking_id', 'in', self.ids),
            ('document_kind', '=', 'loan'),
        ])
        for document in documents:
            picking = document.picking_id
            picking_type = picking.picking_type_id
            if picking.location_id != picking_type.default_location_src_id:
                raise ValidationError(_('The BG Source Location must match its Operation Type.'))
            if not picking.location_dest_id:
                raise ValidationError(_('Select a Destination Location before confirming the BG.'))
            if picking.location_dest_id.company_id and picking.location_dest_id.company_id != picking.company_id:
                raise ValidationError(_('The BG Destination Location must belong to the same company or be shared.'))
            active_moves = picking.move_ids.filtered(lambda move: move.state != 'cancel')
            if any(move.location_dest_id != picking.location_dest_id for move in active_moves):
                raise ValidationError(_('All BG product lines must use the selected Destination Location.'))

    def action_confirm(self):
        self._check_loan_return_documents()
        self._check_loan_return_locations()
        return super().action_confirm()

    def button_validate(self):
        self._check_loan_return_documents()
        self._check_loan_return_locations()
        return super().button_validate()
