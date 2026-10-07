# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LoanReturnExportWizard(models.TransientModel):
    _name = 'buz.loan.return.export.wizard'
    _description = 'Loan and Return Export Wizard'

    date_from = fields.Date(
        string='วันที่เริ่มต้น',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string='วันที่สิ้นสุด',
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )

    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operation Type',
        required=True,
    )

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_('วันที่เริ่มต้นต้องไม่อยู่หลังวันที่สิ้นสุด'))

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref(
            'buz_loan_return_export.action_loan_return_export_xlsx'
        ).report_action(self)

    def _get_utc_date_bounds(self):
        self.ensure_one()
        user_timezone = pytz.timezone(self.env.user.tz or 'UTC')
        local_start = user_timezone.localize(
            datetime.combine(self.date_from, time.min)
        )
        local_end = user_timezone.localize(
            datetime.combine(self.date_to + timedelta(days=1), time.min)
        )
        utc = pytz.UTC
        return (
            local_start.astimezone(utc).replace(tzinfo=None),
            local_end.astimezone(utc).replace(tzinfo=None),
        )

    def _get_picking_domain(self, date_start, date_end, document_field, prefix):
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('date_done', '>=', date_start),
            ('date_done', '<', date_end),
            (document_field, '=like', prefix + '%'),
        ]
        return domain

    def _get_report_data(self):
        self.ensure_one()
        date_start, date_end = self._get_utc_date_bounds()
        picking_model = self.env['stock.picking']

        # ชีตยืมแสดง BG ทั้งหมดตามช่วงวันที่และ Operation Type ที่เลือก
        loan_domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('date_done', '>=', date_start),
            ('date_done', '<', date_end),
            ('name', '=like', 'BG-%'),
            ('picking_type_id', '=', self.picking_type_id.id),
        ]
        loan_pickings = picking_model.search(
            loan_domain,
            order='date_done, name, id',
        )

        return_pickings = picking_model.search(
            self._get_picking_domain(
                date_start, date_end, 'return_doc_no', 'RBG-'
            ),
            order='date_done, name, id',
        )
        return_origins = {
            picking.origin for picking in return_pickings if picking.origin
        }
        if return_origins:
            linked_loan_pickings = picking_model.search([
                ('company_id', '=', self.company_id.id),
                ('state', '=', 'done'),
                ('name', '=like', 'BG-%'),
                ('name', 'in', return_origins),
                ('picking_type_id', '=', self.picking_type_id.id),
            ])
            linked_loan_names = set(linked_loan_pickings.mapped('name'))
            return_pickings = return_pickings.filtered(
                lambda picking: picking.origin in linked_loan_names
            )
        else:
            return_pickings = picking_model.browse()

        balances = self._get_loan_balances(loan_pickings, date_end)
        return {
            'loans': self._get_loan_rows(loan_pickings, balances),
            'returns': self._get_return_rows(return_pickings),
        }

    def _get_loan_balances(self, loan_pickings, date_end):
        """ยอดคงเหลือ ณ วันสิ้นสุด โดยอ้าง Source Document และสินค้า"""
        issued_by_source_product = defaultdict(float)
        loan_keys_by_picking = defaultdict(set)
        loan_products_by_source = defaultdict(set)

        for picking in loan_pickings:
            for move in picking.move_ids:
                if move.state != 'done' or not move.product_id:
                    continue
                key = (picking.name, move.product_id.id)
                issued_quantity = move.product_uom._compute_quantity(
                    move.quantity,
                    move.product_id.uom_id,
                )
                issued_by_source_product[key] += issued_quantity
                loan_keys_by_picking[picking.id].add(key)
                loan_products_by_source[picking.name].add(move.product_id.id)

        loan_names = list(loan_products_by_source)
        if not loan_names:
            return {}

        return_domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('date_done', '<', date_end),
            ('return_doc_no', '=like', 'RBG-%'),
            ('origin', 'in', loan_names),
        ]

        return_pickings = self.env['stock.picking'].search(
            return_domain,
            order='date_done, name, id',
        )

        returned_by_source_product = defaultdict(float)
        for picking in return_pickings:
            for move in picking.move_ids:
                if move.state != 'done' or not move.product_id:
                    continue
                key = (picking.origin or '', move.product_id.id)
                if move.product_id.id not in loan_products_by_source.get(key[0], set()):
                    continue
                returned_quantity = move.product_uom._compute_quantity(
                    move.quantity,
                    move.product_id.uom_id,
                )
                returned_by_source_product[key] += returned_quantity

        balances = {}
        for picking in loan_pickings:
            for key in loan_keys_by_picking.get(picking.id, set()):
                remaining = (
                    issued_by_source_product[key]
                    - returned_by_source_product.get(key, 0.0)
                )
                balances[(picking.id, key[1])] = remaining
        return balances

    def _as_user_date(self, value):
        if not value:
            return False
        return fields.Datetime.context_timestamp(self, value).date()

    def _get_loan_rows(self, pickings, balances):
        rows = []
        for picking in pickings:
            product_rows = {}
            for move in picking.move_ids.sorted(lambda item: (item.sequence, item.id)):
                if move.state != 'done' or not move.product_id:
                    continue
                product = move.product_id
                if product.id not in product_rows:
                    product_rows[product.id] = {
                        'product': product,
                        'quantity': 0.0,
                    }
                product_rows[product.id]['quantity'] += move.product_uom._compute_quantity(
                    move.quantity,
                    product.uom_id,
                )

            partner = picking.partner_id
            for product_id, item in product_rows.items():
                product = item['product']
                rows.append([
                    len(rows) + 1,
                    picking.name or '',
                    self._as_user_date(picking.date_done),
                    (partner.ref or '') if partner else '',
                    (partner.name or '') if partner else '',
                    product.default_code or '',
                    product.name or '',
                    item['quantity'],
                    balances.get((picking.id, product_id), item['quantity']),
                    self._as_user_date(picking.scheduled_date),
                    partner._display_address(without_company=True) if partner else '',
                    picking.location_dest_id.complete_name or '',
                ])
        return rows

    def _get_return_rows(self, pickings):
        rows = []
        state_selection = dict(
            self.env['stock.picking']._fields['state']._description_selection(self.env)
        )
        for picking in pickings:
            product_rows = {}
            for move in picking.move_ids.sorted(lambda item: (item.sequence, item.id)):
                if move.state != 'done' or not move.product_id:
                    continue
                product = move.product_id
                if product.id not in product_rows:
                    product_rows[product.id] = {
                        'product': product,
                        'quantity': 0.0,
                    }
                product_rows[product.id]['quantity'] += move.product_uom._compute_quantity(
                    move.quantity,
                    product.uom_id,
                )

            partner = picking.partner_id
            for item in product_rows.values():
                product = item['product']
                rows.append([
                    len(rows) + 1,
                    picking.return_doc_no or '',
                    self._as_user_date(picking.date_done),
                    product.default_code or '',
                    product.name or '',
                    item['quantity'],
                    (partner.ref or '') if partner else '',
                    (partner.name or '') if partner else '',
                    picking.origin or '',
                    self._as_user_date(picking.scheduled_date),
                    picking.user_id.name or '' if picking.user_id else '',
                    self._as_user_date(picking.date_confirmed),
                    state_selection.get(picking.state, picking.state),
                    self._as_user_date(picking.date_done),
                    picking.department_install or '',
                    picking.notes or '',
                ])
        return rows

