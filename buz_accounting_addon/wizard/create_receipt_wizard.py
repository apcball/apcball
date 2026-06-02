# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CreateReceiptWizard(models.TransientModel):
    _name = 'buz.create.receipt.wizard'
    _description = 'Wizard to select document date before creating receipt'

    date = fields.Date(
        string='Document Date',
        required=True,
        default=fields.Date.context_today,
        help='Date for the receipt document. The receipt number will be generated based on this date.',
    )
    invoice_ids = fields.Many2many(
        'account.move',
        string='Invoices',
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_create_receipt(self):
        """Create the receipt using the wizard date, then open it."""
        self.ensure_one()
        moves = self.invoice_ids
        if not moves:
            raise UserError(_("No invoices found to create receipt."))

        valid_moves = moves.filtered(
            lambda m: m.state == 'posted'
            and m.move_type in ['out_invoice', 'out_refund']
        )

        # Re-validate: already used in other receipts
        existing_lines = self.env['account.receipt.line'].search(
            [('move_id', 'in', valid_moves.ids)]
        )
        if existing_lines:
            names = [ln.move_id.name for ln in existing_lines]
            raise UserError(
                _("The following invoices are already used in receipts: %s")
                % ", ".join(names)
            )

        if not valid_moves:
            raise UserError(_("No valid invoices found for receipt creation."))

        first_move = valid_moves[0]
        delivery_partner = first_move.partner_shipping_id or first_move.partner_id

        receipt = self.env['account.receipt'].create({
            'partner_id': first_move.partner_id.id,
            'date': self.date,
            'line_ids': [],
            'delivery_partner_id': delivery_partner.id if delivery_partner else False,
        })

        lines_vals = []
        for mv in valid_moves:
            total = mv.amount_total_signed if mv.move_type == 'out_refund' else mv.amount_total
            residual = mv.amount_residual_signed if mv.move_type == 'out_refund' else mv.amount_residual
            lines_vals.append((0, 0, {
                'move_id': mv.id,
                'amount_total': total,
                'amount_residual': residual,
            }))
        receipt.write({'line_ids': lines_vals})

        # Auto-post if enabled — action_post now uses receipt.date for sequence
        auto_post = self.env['ir.config_parameter'].sudo().get_param(
            'buz_accounting_addon.auto_post_receipts', default=True
        )
        if auto_post:
            receipt.action_post()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.receipt',
            'view_mode': 'form',
            'res_id': receipt.id,
            'target': 'current',
        }
