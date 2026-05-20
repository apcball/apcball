# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json


class SoCreditNoteWizard(models.TransientModel):
    """Wizard for creating credit notes from Sale Orders"""

    _name = 'so.credit.note.wizard'
    _description = 'SO Credit Note Wizard'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        required=True,
        readonly=True
    )
    line_ids = fields.One2many(
        'so.credit.note.wizard.line',
        'wizard_id',
        string='Lines'
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('type', '=', 'sale')]",
        required=True
    )
    date = fields.Date(
        string='Date',
        default=fields.Date.context_today,
        required=True
    )
    reason = fields.Text(
        string='Reason',
        help='Reason for creating this credit note'
    )

    @api.model
    def _get_default_journal(self, company):
        return self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', company.id),
        ], limit=1)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        sale_order_id = vals.get('sale_order_id') or self.env.context.get('default_sale_order_id')
        if sale_order_id and not vals.get('journal_id'):
            sale_order = self.env['sale.order'].browse(sale_order_id)
            journal = self._get_default_journal(sale_order.company_id)
            if journal:
                vals['journal_id'] = journal.id
        return vals

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id(self):
        """Set default journal based on SO's currency and company"""
        if self.sale_order_id:
            journal = self._get_default_journal(self.sale_order_id.company_id)
            if journal:
                self.journal_id = journal.id

    def action_create_credit_note(self):
        """Create credit note from selected SO lines"""
        self.ensure_one()

        # Filter selected lines
        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_('Please select at least one line to create a credit note.'))

        # Prepare credit note values
        move_vals = {
            'move_type': 'out_refund',
            'partner_id': self.sale_order_id.partner_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.sale_order_id.currency_id.id,
            'invoice_date': self.date,
            'ref': f'CN/{self.sale_order_id.name}',
            'narration': self.reason,
            'source_so_id': self.sale_order_id.id,
        }

        # Create credit note
        move = self.env['account.move'].create(move_vals)

        # Create credit note lines
        line_tracking = []
        for wizard_line in selected_lines:
            so_line = wizard_line.so_line_id

            # Get account from product
            if so_line.product_id:
                account = so_line.product_id.property_account_income_id or \
                         so_line.product_id.categ_id.property_account_income_categ_id
            else:
                account = self.journal_id.default_account_id

            if not account:
                raise UserError(_(
                    'Please define an income account for product "%s".' % so_line.product_id.name
                ))

            # Create credit note line
            self.env['account.move.line'].create({
                'move_id': move.id,
                'product_id': so_line.product_id.id,
                'name': so_line.name,
                'quantity': wizard_line.qty_to_refund,
                'price_unit': wizard_line.price_unit,
                'account_id': account.id,
                'sale_line_id': so_line.id,
                'tax_ids': [(6, 0, so_line.tax_id.ids)],
            })

            # Track source line
            line_tracking.append({
                'so_line_id': so_line.id,
                'product_id': so_line.product_id.id,
                'quantity': wizard_line.qty_to_refund,
                'price_unit': wizard_line.price_unit,
            })

        # Save source lines tracking
        move.source_line_ids = json.dumps(line_tracking)

        # Validate credit note
        try:
            move.action_post()
        except Exception as e:
            # If validation fails, don't validate but still return
            pass

        # Close wizard and open credit note
        return {
            'type': 'ir.actions.act_window',
            'name': 'Credit Note',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SoCreditNoteWizardLine(models.TransientModel):
    """Wizard lines for SO credit note"""

    _name = 'so.credit.note.wizard.line'
    _description = 'SO Credit Note Wizard Line'

    wizard_id = fields.Many2one(
        'so.credit.note.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    so_line_id = fields.Many2one(
        'sale.order.line',
        string='SO Line',
        required=True,
        readonly=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        readonly=True
    )
    ordered_qty = fields.Float(
        string='Ordered Qty',
        digits='Product Unit of Measure',
        readonly=True
    )
    delivered_qty = fields.Float(
        string='Delivered Qty',
        digits='Product Unit of Measure',
        readonly=True
    )
    invoiced_qty = fields.Float(
        string='Invoiced Qty',
        digits='Product Unit of Measure',
        readonly=True
    )
    qty_to_refund = fields.Float(
        string='Qty to Refund',
        digits='Product Unit of Measure',
        required=True
    )
    price_unit = fields.Float(
        string='Unit Price',
        digits='Product Price',
        readonly=True
    )
    selected = fields.Boolean(
        string='Selected',
        default=True
    )
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True
    )

    @api.onchange('so_line_id')
    def _onchange_so_line_id(self):
        """Set default refund qty based on delivered - invoiced"""
        if self.so_line_id:
            self.qty_to_refund = self.so_line_id.qty_delivered - self.so_line_id.qty_invoiced

    @api.depends('qty_to_refund', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty_to_refund * line.price_unit
