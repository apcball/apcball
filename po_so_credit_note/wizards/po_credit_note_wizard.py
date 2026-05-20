# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json


class PoCreditNoteWizard(models.TransientModel):
    """Wizard for creating credit notes from Purchase Orders"""

    _name = 'po.credit.note.wizard'
    _description = 'PO Credit Note Wizard'

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=True,
        readonly=True
    )
    line_ids = fields.One2many(
        'po.credit.note.wizard.line',
        'wizard_id',
        string='Lines'
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('type', '=', 'purchase')]",
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
            ('type', '=', 'purchase'),
            ('company_id', '=', company.id),
        ], limit=1)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        purchase_order_id = vals.get('purchase_order_id') or self.env.context.get('default_purchase_order_id')
        if purchase_order_id and not vals.get('journal_id'):
            purchase_order = self.env['purchase.order'].browse(purchase_order_id)
            journal = self._get_default_journal(purchase_order.company_id)
            if journal:
                vals['journal_id'] = journal.id
        return vals

    @api.onchange('purchase_order_id')
    def _onchange_purchase_order_id(self):
        """Set default journal based on PO's currency and company"""
        if self.purchase_order_id:
            journal = self._get_default_journal(self.purchase_order_id.company_id)
            if journal:
                self.journal_id = journal.id

    def action_create_credit_note(self):
        """Create credit note from selected PO lines"""
        self.ensure_one()

        # Filter selected lines
        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_('Please select at least one line to create a credit note.'))

        # Prepare credit note values
        move_vals = {
            'move_type': 'in_refund',
            'partner_id': self.purchase_order_id.partner_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.purchase_order_id.currency_id.id,
            'invoice_date': self.date,
            'ref': f'CN/{self.purchase_order_id.name}',
            'narration': self.reason,
            'source_po_id': self.purchase_order_id.id,
        }

        # Create credit note
        move = self.env['account.move'].create(move_vals)

        # Create credit note lines
        line_tracking = []
        for wizard_line in selected_lines:
            po_line = wizard_line.po_line_id

            # Get account from product
            if po_line.product_id:
                account = po_line.product_id.property_account_expense_id or \
                         po_line.product_id.categ_id.property_account_expense_categ_id
            else:
                account = self.journal_id.default_account_id

            if not account:
                raise UserError(_(
                    'Please define an expense account for product "%s".' % po_line.product_id.name
                ))

            # Create credit note line
            self.env['account.move.line'].create({
                'move_id': move.id,
                'product_id': po_line.product_id.id,
                'name': po_line.name,
                'quantity': wizard_line.product_qty,
                'price_unit': wizard_line.price_unit,
                'account_id': account.id,
                'purchase_line_id': po_line.id,
                'tax_ids': [(6, 0, po_line.taxes_id.ids)],
            })

            # Track source line
            line_tracking.append({
                'po_line_id': po_line.id,
                'product_id': po_line.product_id.id,
                'quantity': wizard_line.product_qty,
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


class PoCreditNoteWizardLine(models.TransientModel):
    """Wizard lines for PO credit note"""

    _name = 'po.credit.note.wizard.line'
    _description = 'PO Credit Note Wizard Line'

    wizard_id = fields.Many2one(
        'po.credit.note.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    po_line_id = fields.Many2one(
        'purchase.order.line',
        string='PO Line',
        required=True,
        readonly=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        readonly=True
    )
    product_qty = fields.Float(
        string='Quantity',
        digits='Product Unit of Measure',
        readonly=True
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

    @api.depends('product_qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.product_qty * line.price_unit
