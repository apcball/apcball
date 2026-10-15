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
            role = vals.get('loan_return_role')
            if not role:
                continue
            picking_type = self.env['stock.picking.type'].browse(
                vals.get('picking_type_id') or self.env.context.get('default_picking_type_id')
            ).exists()
            if not picking_type or picking_type.code != 'internal':
                raise ValidationError(_('Show loan and return documents require an Internal Transfer type.'))

            markers = ' '.join((
                picking_type.sequence_code or '',
                picking_type.sequence_id.prefix or '',
            )).upper()
            if role == 'loan':
                loan_type = vals.get('loan_return_type')
                expected_marker = 'BG-' + (loan_type or '').upper()
                if loan_type not in ('rt', 'pj', 'ol') or expected_marker not in markers:
                    raise ValidationError(_('Select the matching RT, PJ, or OL Operation Type.'))
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
            'target': 'new',
            'context': {'default_source_picking_id': root.id},
        }
