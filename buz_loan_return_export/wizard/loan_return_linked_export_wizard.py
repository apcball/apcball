# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class LoanReturnLinkedExportWizard(models.TransientModel):
    _name = 'buz.loan.return.linked.export.wizard'
    _description = 'Linked BG/RBG Export Wizard'

    date_from = fields.Date(required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_('Start date must not be after end date.'))

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref(
            'buz_loan_return_export.action_loan_return_linked_export_xlsx'
        ).report_action(self)

    def _get_utc_date_bounds(self):
        self.ensure_one()
        timezone = pytz.timezone(self.env.user.tz or 'UTC')
        start = timezone.localize(datetime.combine(self.date_from, time.min))
        end = timezone.localize(datetime.combine(self.date_to + timedelta(days=1), time.min))
        return start.astimezone(pytz.UTC).replace(tzinfo=None), end.astimezone(pytz.UTC).replace(tzinfo=None)

    def _get_report_rows(self):
        self.ensure_one()
        start, end = self._get_utc_date_bounds()
        documents = self.env['buz.loan.return.document'].search([
            ('document_kind', '=', 'loan'),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('picking_id.date_done', '>=', start),
            ('picking_id.date_done', '<', end),
        ], order='picking_id.date_done, name, id')
        rows = []
        for document in documents:
            return_documents = document.return_document_ids.filtered(
                lambda item: item.state == 'done'
                and item.picking_id.date_done and item.picking_id.date_done < end
            )
            return_pickings = return_documents.mapped('picking_id') | return_documents.mapped('backorder_picking_ids')
            missing_links = any(
                move.state == 'done' and move.product_id
                and not move.loan_return_source_move_id
                for picking in return_pickings
                for move in picking.move_ids
            )
            loan_pickings = document.picking_id | document.backorder_picking_ids
            loan_moves = loan_pickings.mapped('move_ids').filtered(
                lambda move: move.state == 'done' and move.product_id
                and move.picking_id.date_done and move.picking_id.date_done < end
            ).sorted(lambda move: (move.sequence, move.id))
            for loan_move in loan_moves:
                returned = 0.0
                linked_return_moves = loan_move.loan_return_return_move_ids.filtered(
                    lambda move: move.state == 'done'
                    and move.picking_id.date_done and move.picking_id.date_done < end
                )
                for return_move in linked_return_moves:
                    returned += return_move.product_uom._compute_quantity(
                        return_move.quantity, loan_move.product_uom,
                    )
                balance = loan_move.quantity - returned
                warning = ''
                if float_compare(balance, 0, precision_rounding=loan_move.product_uom.rounding) < 0:
                    warning = _('Returned quantity exceeds the loan quantity; values are shown as recorded.')
                elif missing_links:
                    warning = _('Some completed RBG lines have no direct BG item link and are excluded from returned quantity.')
                rows.append({
                    'bg': document.name,
                    'bg_date': loan_move.picking_id.date_done,
                    'rbg': ', '.join(sorted(set(linked_return_moves.mapped('picking_id.name')))),
                    'partner': document.partner_id.display_name,
                    'product_code': loan_move.product_id.default_code or '',
                    'product': loan_move.product_id.display_name,
                    'uom': loan_move.product_uom.name,
                    'loaned': loan_move.quantity,
                    'returned': returned,
                    'balance': balance,
                    'warning': warning,
                })
        return rows