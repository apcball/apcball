# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    loan_return_role = fields.Selection(
        [('loan', 'Show Loan (BG)'), ('return', 'Show Return (RBG)')],
        string='Loan / Return Document', index=True, copy=False,
    )
    loan_return_type = fields.Selection(
        [('rt', 'RT'), ('pj', 'PJ'), ('ol', 'OL')],
        string='Show Loan Type', copy=False,
    )
    loan_return_source_id = fields.Many2one(
        'stock.picking', string='Source Loan Document', index=True,
        check_company=True, ondelete='restrict', copy=False,
    )
    loan_return_root_id = fields.Many2one(
        'stock.picking', string='Original Loan Transfer', index=True,
        check_company=True, ondelete='restrict', copy=False,
    )
    loan_return_ids = fields.One2many(
        'stock.picking', 'loan_return_source_id', string='Show Returns',
    )
    loan_return_backorder_ids = fields.One2many(
        'stock.picking', 'loan_return_root_id', string='Loan Backorders',
    )
    loan_return_operation_type_ids = fields.Many2many(
        'stock.picking.type',
        compute='_compute_loan_return_operation_type_options',
    )
    loan_return_no_operation_type = fields.Boolean(
        compute='_compute_loan_return_operation_type_options',
    )

    @staticmethod
    def _loan_type_markers(picking_type):
        markers = ' '.join((
            picking_type.sequence_code or '',
            picking_type.sequence_id.prefix or '',
        )).upper()
        return [
            loan_type
            for loan_type in ('rt', 'pj', 'ol')
            if 'BG-' + loan_type.upper() in markers
        ]

    @api.model
    def _get_loan_operation_types(self, company_id=None):
        company = (
            self.env['res.company'].browse(company_id).exists()
            if company_id else self.env.company
        )
        candidates = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ])
        return candidates.filtered(lambda item: len(self._loan_type_markers(item)) == 1)

    @api.depends('company_id', 'loan_return_role')
    def _compute_loan_return_operation_type_options(self):
        for picking in self:
            if picking.loan_return_role == 'loan':
                operation_types = self._get_loan_operation_types(
                    picking.company_id.id or self.env.company.id,
                )
            else:
                operation_types = self.env['stock.picking.type']
            picking.loan_return_operation_type_ids = operation_types
            picking.loan_return_no_operation_type = (
                picking.loan_return_role == 'loan' and not operation_types
            )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        role = values.get('loan_return_role') or self.env.context.get('default_loan_return_role')
        if role != 'loan':
            return values

        company_id = (
            values.get('company_id')
            or self.env.context.get('default_company_id')
            or self.env.company.id
        )
        operation_types = self._get_loan_operation_types(company_id)
        if len(operation_types) != 1:
            for field_name in ('picking_type_id', 'location_id', 'location_dest_id'):
                if field_name in fields_list:
                    values[field_name] = False
            return values

        operation_type = operation_types[0]
        defaults = {
            'picking_type_id': operation_type.id,
            'company_id': company_id,
            'location_id': operation_type.default_location_src_id.id,
            'location_dest_id': operation_type.default_location_dest_id.id,
        }
        values.update({
            field_name: value
            for field_name, value in defaults.items()
            if field_name in fields_list
        })
        return values

    @staticmethod
    def _loan_type_from_operation_type(picking_type):
        """อ่าน marker เพื่อระบุประเภท RT, PJ หรือ OL จาก Operation Type"""
        matches = StockPicking._loan_type_markers(picking_type)
        if len(matches) != 1:
            raise ValidationError(_('The Operation Type sequence must identify exactly one loan type: RT, PJ, or OL.'))
        return matches[0]

    @api.model_create_multi
    def create(self, vals_list):
        source_ids = [
            vals.get('loan_return_source_id')
            for vals in vals_list
            if vals.get('loan_return_role') == 'return'
            and vals.get('loan_return_source_id')
        ]
        self._lock_loan_sources(self.browse(source_ids).exists())

        for vals in vals_list:
            role = vals.get('loan_return_role') or self.env.context.get('default_loan_return_role')
            if not role:
                continue
            vals['loan_return_role'] = role
            picking_type = self.env['stock.picking.type'].browse(
                vals.get('picking_type_id') or self.env.context.get('default_picking_type_id')
            ).exists()
            if role == 'loan' and not picking_type:
                raise ValidationError(_(
                    'No active BG Operation Type is available for this company. '
                    'Configure an active Internal Transfer with exactly one BG-RT, BG-PJ, or BG-OL marker.'
                ))
            if not picking_type or not picking_type.active or picking_type.code != 'internal':
                raise ValidationError(_('Show loan and return documents require an Internal Transfer type.'))

            markers = ' '.join((
                picking_type.sequence_code or '',
                picking_type.sequence_id.prefix or '',
            )).upper()
            if role == 'loan':
                company_id = (
                    vals.get('company_id')
                    or self.env.context.get('default_company_id')
                    or self.env.company.id
                )
                vals['company_id'] = company_id
                if picking_type.company_id and picking_type.company_id.id != company_id:
                    raise ValidationError(_('Select an Operation Type for the current company.'))
                vals['loan_return_type'] = self._loan_type_from_operation_type(picking_type)
            elif role == 'return':
                source = self.browse(vals.get('loan_return_source_id')).exists()
                if not source or source.loan_return_role != 'loan':
                    raise ValidationError(_('A return must reference a tracked show-loan document.'))
                if source.state != 'done':
                    raise ValidationError(_('The loan transfer must be completed before it can be returned.'))
                if 'RBG' not in markers:
                    raise ValidationError(_('Select the RBG Operation Type for a show return.'))
                root = source.loan_return_root_id or source
                vals['loan_return_source_id'] = root.id
                vals['origin'] = root.name
            else:
                raise ValidationError(_('Invalid show-loan document role.'))

        records = super().create(vals_list)
        records.filtered(lambda picking: picking.loan_return_role == 'return')._check_loan_return_limits()
        return records

    @api.model
    def _lock_loan_sources(self, sources):
        """ล็อกใบยืมก่อนคำนวณยอด เพื่อไม่ให้ผู้ใช้สองคนจองยอดคืนซ้อนกัน"""
        source_ids = sorted(set(sources.ids))
        if not source_ids:
            return
        self.env.flush_all()
        self.env.cr.execute(
            'SELECT id FROM stock_picking WHERE id = ANY(%s) ORDER BY id FOR UPDATE',
            [source_ids],
        )
        self.env['stock.picking'].invalidate_model()
        self.env['stock.move'].invalidate_model()

    def _loan_family(self):
        self.ensure_one()
        root = self.loan_return_root_id or self
        return self.search([
            '&', ('loan_return_role', '=', 'loan'),
            '|', ('id', '=', root.id), ('loan_return_root_id', '=', root.id),
        ])

    def _get_done_loan_quantities(self):
        """Return quantities actually moved, grouped in each product's base UoM."""
        self.ensure_one()
        quantities = defaultdict(float)
        for picking in self._loan_family():
            for move in picking.move_ids.filtered(lambda item: item.state == 'done'):
                product = move.product_id
                if product.type == 'service':
                    continue
                quantities[product.id] += move.product_uom._compute_quantity(
                    move.quantity, product.uom_id, round=False,
                )
        return quantities

    def _get_reserved_return_quantities(self):
        self.ensure_one()
        quantities = defaultdict(float)
        returns = self.search([
            ('loan_return_role', '=', 'return'),
            ('loan_return_source_id', '=', self.id),
            ('state', '!=', 'cancel'),
        ])
        for picking in returns:
            for move in picking.move_ids.filtered(lambda item: item.state != 'cancel'):
                product = move.product_id
                if product.type == 'service':
                    continue
                # ใบ Done ใช้จำนวนที่รับจริง ส่วนใบที่ยังเปิดใช้จำนวนที่จองคืนไว้
                moved_qty = move.quantity if move.state == 'done' else move.product_uom_qty
                quantities[product.id] += move.product_uom._compute_quantity(
                    moved_qty, product.uom_id, round=False,
                )
        return quantities

    def _get_loan_return_balances(self):
        self.ensure_one()
        root = self.loan_return_root_id or self
        delivered = root._get_done_loan_quantities()
        reserved = root._get_reserved_return_quantities()
        product_ids = delivered.keys() | reserved.keys()
        return {
            product_id: {
                'delivered': delivered.get(product_id, 0.0),
                'reserved': reserved.get(product_id, 0.0),
                'remaining': delivered.get(product_id, 0.0) - reserved.get(product_id, 0.0),
            }
            for product_id in product_ids
        }

    def _check_loan_return_limits(self):
        returns = self.filtered(lambda picking: picking.loan_return_role == 'return')
        sources = returns.mapped('loan_return_source_id')
        self._lock_loan_sources(sources)
        for source in sources:
            for product_id, balance in source._get_loan_return_balances().items():
                product = self.env['product.product'].browse(product_id)
                if float_compare(
                    balance['remaining'], 0.0,
                    precision_rounding=product.uom_id.rounding,
                ) < 0:
                    raise ValidationError(_(
                        'The total return quantity for %(product)s exceeds the quantity actually transferred from %(loan)s.',
                        product=product.display_name,
                        loan=source.display_name,
                    ))

    def button_validate(self):
        returns = self.filtered(lambda picking: picking.loan_return_role == 'return')
        if returns:
            returns._check_loan_return_limits()
        return super().button_validate()

    def _create_backorder_picking(self):
        self.ensure_one()
        backorder = super()._create_backorder_picking()
        if self.loan_return_role == 'loan':
            backorder.write({
                'loan_return_role': 'loan',
                'loan_return_type': self.loan_return_type,
                'loan_return_root_id': self.loan_return_root_id.id or self.id,
            })
        elif self.loan_return_role == 'return':
            backorder.write({
                'loan_return_role': 'return',
                'loan_return_source_id': self.loan_return_source_id.id,
                'origin': self.loan_return_source_id.name,
            })
        return backorder

    def action_open_return_wizard(self):
        self.ensure_one()
        root = self.loan_return_root_id or self
        if root.loan_return_role != 'loan':
            raise UserError(_('Only a tracked show-loan document can start a return.'))
        if root.state != 'done':
            raise UserError(_('The loan transfer must be completed before it can be returned.'))
        balances = root._get_loan_return_balances()
        if not any(value['remaining'] > 0 for value in balances.values()):
            raise UserError(_('There are no remaining delivered quantities to return.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Show Return'),
            'res_model': 'buz.loan.return.return.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('buz_loan_return.view_buz_loan_return_return_wizard_form').id,
            'target': 'current',
            'context': {'default_source_picking_id': root.id},
        }
