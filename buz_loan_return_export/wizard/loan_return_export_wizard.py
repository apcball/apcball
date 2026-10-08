# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression


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

    @staticmethod
    def _get_source_bg_name(origin):
        """Extract the BG document number from Source Document."""
        if not origin:
            return ''
        source_name = origin.split('/', 1)[0].strip()
        return source_name if source_name.startswith('BG-') else ''

    def _get_report_data(self):
        self.ensure_one()
        date_start, date_end = self._get_utc_date_bounds()
        picking_model = self.env['stock.picking']

        return_domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('date_done', '>=', date_start),
            ('date_done', '<', date_end),
        ] + expression.OR([
            [('name', '=like', 'RBG/%')],
            [('name', '=like', 'RBG-%')],
        ])
        return_domain.append(('picking_type_id', '=', self.picking_type_id.id))
        return_pickings = picking_model.search(
            return_domain,
            order='date_done, name, id',
        )

        source_bg_names = {
            self._get_source_bg_name(picking.origin)
            for picking in return_pickings
        }
        source_bg_names.discard('')

        loan_pickings = picking_model.browse()
        if source_bg_names:
            source_bg_candidates = picking_model.search([
                ('company_id', '=', self.company_id.id),
                ('state', '=', 'done'),
                ('name', '=like', 'BG-%'),
                ('name', 'in', list(source_bg_names)),
            ], order='date_done, name, id')

            # แสดง BG เฉพาะเลขที่พบเอกสารต้นทางเพียงรายการเดียว
            candidate_counts = defaultdict(int)
            for picking in source_bg_candidates:
                candidate_counts[picking.name] += 1
            unique_source_names = {
                name for name, count in candidate_counts.items() if count == 1
            }
            loan_pickings = source_bg_candidates.filtered(
                lambda picking: picking.name in unique_source_names
            )

        return {
            'loans': self._get_loan_rows(loan_pickings),
            'returns': self._get_return_rows(return_pickings),
        }

    def _as_user_date(self, value):
        if not value:
            return False
        return fields.Datetime.context_timestamp(self, value).date()

    def _get_loan_rows(self, pickings):
        rows = []
        for picking in pickings:
            partner = picking.partner_id
            for move in picking.move_ids.sorted(lambda item: (item.sequence, item.id)):
                if move.state != 'done' or not move.product_id:
                    continue
                product = move.product_id
                rows.append([
                    len(rows) + 1,
                    picking.name or '',
                    self._as_user_date(picking.date_done),
                    (partner.ref or '') if partner else '',
                    (partner.name or '') if partner else '',
                    product.default_code or '',
                    product.name or '',
                    move.quantity,
                    None,
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
            partner = picking.partner_id
            for move in picking.move_ids.sorted(lambda item: (item.sequence, item.id)):
                if move.state != 'done' or not move.product_id:
                    continue
                product = move.product_id
                rows.append([
                    len(rows) + 1,
                    picking.name or '',
                    self._as_user_date(picking.date_confirmed),
                    product.default_code or '',
                    product.name or '',
                    move.quantity,
                    (partner.ref or '') if partner else '',
                    (partner.name or '') if partner else '',
                    picking.origin or '',
                    self._as_user_date(picking.scheduled_date),
                    picking.user_id.name or '' if picking.user_id else '',
                    state_selection.get(picking.state, picking.state),
                    self._as_user_date(picking.date_done),
                    picking.department_install or '',
                    picking.notes or '',
                ])
        return rows
