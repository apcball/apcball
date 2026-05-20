from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderCreditNoteWizard(models.TransientModel):
    _name = "sale.order.credit.note.wizard"
    _description = "Sale Order Credit Note Wizard"

    sale_id = fields.Many2one(
        "sale.order",
        string="Sale Order",
        required=True,
        readonly=True,
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="Invoice",
        required=False,
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('id', 'in', allowed_invoice_ids)]",
    )
    allowed_invoice_ids = fields.Many2many(
        "account.move",
        compute="_compute_allowed_invoice_ids",
    )
    reason = fields.Text(
        string="Reason",
        default="Credit note from Sale Order",
    )
    line_ids = fields.One2many(
        "sale.order.credit.note.wizard.line",
        "wizard_id",
        string="Lines",
    )

    @api.depends("sale_id")
    def _compute_allowed_invoice_ids(self):
        for wizard in self:
            if wizard.sale_id:
                wizard.allowed_invoice_ids = wizard.sale_id.invoice_ids.filtered(
                    lambda inv: inv.move_type == "out_invoice"
                    and inv.state == "posted"
                )
            else:
                wizard.allowed_invoice_ids = False

    @api.onchange("sale_id")
    def _onchange_sale_id(self):
        if self.sale_id:
            invoices = self.sale_id.invoice_ids.filtered(
                lambda inv: inv.move_type == "out_invoice"
                and inv.state == "posted"
            )
            if len(invoices) == 1:
                self.invoice_id = invoices
            else:
                self.invoice_id = False
            self._load_lines()

    @api.onchange("invoice_id")
    def _onchange_invoice_id(self):
        self._load_lines()

    def _load_lines(self):
        """Populate wizard lines from the selected invoice or negative SO lines."""
        self.line_ids = [(5, 0, 0)]  # clear existing
        lines_vals = []
        
        if self.invoice_id:
            sale_lines = self.sale_id.order_line
            for inv_line in self.invoice_id.invoice_line_ids:
                if inv_line.display_type or not inv_line.product_id:
                    continue
                if not inv_line.sale_line_ids:
                    continue
                if not any(sl in sale_lines for sl in inv_line.sale_line_ids):
                    continue

                invoiced_qty = inv_line.quantity
                credited_qty = self._get_credited_qty(inv_line)
                refundable_qty = invoiced_qty - credited_qty
                if refundable_qty <= 0:
                    continue

                lines_vals.append((0, 0, {
                    "sale_line_id": inv_line.sale_line_ids[0].id,
                    "invoice_line_id": inv_line.id,
                    "product_id": inv_line.product_id.id,
                    "name": inv_line.name,
                    "invoiced_qty": invoiced_qty,
                    "credited_qty": credited_qty,
                    "refundable_qty": refundable_qty,
                    "credit_qty": 0.0,
                    "price_unit": inv_line.price_unit,
                    "discount": inv_line.discount,
                    "tax_ids": [(6, 0, inv_line.tax_ids.ids)],
                }))
                
        # Handle negative SO lines directly, regardless of whether invoice_id is selected
        for sl in self.sale_id.order_line:
            if sl.display_type or not sl.product_id:
                continue
            if sl.product_uom_qty >= 0:
                continue
            
            # For negative lines, qty is negative.
            invoiced_qty = abs(sl.qty_invoiced)
            credited_qty = 0.0 # Handled by standard invoicing logic mostly
            refundable_qty = abs(sl.product_uom_qty) - invoiced_qty
            
            if refundable_qty <= 0:
                continue
                
            lines_vals.append((0, 0, {
                "sale_line_id": sl.id,
                "invoice_line_id": False,
                "product_id": sl.product_id.id,
                "name": sl.name,
                "invoiced_qty": invoiced_qty,
                "credited_qty": credited_qty,
                "refundable_qty": refundable_qty,
                "credit_qty": 0.0,
                "price_unit": sl.price_unit,
                "discount": sl.discount,
                "tax_ids": [(6, 0, sl.tax_id.ids)],
            }))
            
        self.line_ids = lines_vals

    def _get_credited_qty(self, invoice_line):
        """Calculate the quantity already credited for an invoice line.

        Looks at posted and draft credit notes that reverse the same invoice
        and reference the same source invoice line.
        """
        CreditNoteLine = self.env["account.move.line"]
        # Find credit notes that reverse the same invoice
        credit_notes = self.env["account.move"].search([
            ("reversed_entry_id", "=", self.invoice_id.id),
            ("move_type", "=", "out_refund"),
            ("state", "in", ["draft", "posted"]),
        ])
        if not credit_notes:
            return 0.0

        # Primary: sum quantities from credit note lines linked via
        # source_invoice_line_id (set by this module)
        credited_lines = CreditNoteLine.search([
            ("move_id", "in", credit_notes.ids),
            ("source_invoice_line_id", "=", invoice_line.id),
        ])
        if credited_lines:
            return sum(credited_lines.mapped("quantity"))

        # Fallback: for credit notes created before this module was installed,
        # match by product + name to avoid over-counting when the same product
        # appears on multiple invoice lines.
        product_lines = CreditNoteLine.search([
            ("move_id", "in", credit_notes.ids),
            ("product_id", "=", invoice_line.product_id.id),
            ("name", "=", invoice_line.name),
            ("display_type", "=", False),
        ])
        return sum(product_lines.mapped("quantity"))

    def action_create_credit_note(self):
        """Validate and create the credit note."""
        self.ensure_one()

        selected_lines = self.line_ids.filtered(lambda l: l.selected)
        if not selected_lines:
            raise UserError(_("You must select at least one line to credit."))

        for line in selected_lines:
            if line.credit_qty <= 0:
                raise UserError(
                    _("Credit quantity must be greater than zero for line '%s'.")
                    % line.name
                )
            if line.credit_qty > line.refundable_qty:
                raise UserError(
                    _(
                        "Credit quantity (%(qty)s) cannot exceed refundable "
                        "quantity (%(refundable)s) for line '%(name)s'."
                    ),
                    qty=line.credit_qty,
                    refundable=line.refundable_qty,
                    name=line.name,
                )
            if line.invoice_line_id and line.invoice_line_id.move_id != self.invoice_id:
                raise UserError(
                    _("Line '%s' does not belong to the selected invoice.") % line.name
                )

        # Build credit note lines
        credit_note_lines = []
        for line in selected_lines:
            line_vals = {
                "product_id": line.product_id.id,
                "name": line.name,
                "quantity": line.credit_qty,
                "price_unit": line.price_unit,
                "discount": line.discount,
                "tax_ids": [(6, 0, line.tax_ids.ids)],
                "sale_line_ids": [(6, 0, line.sale_line_id.ids)],
                "source_sale_line_id": line.sale_line_id.id,
            }
            
            if line.invoice_line_id:
                inv_line = line.invoice_line_id
                line_vals["source_invoice_line_id"] = inv_line.id
                if inv_line.account_id:
                    line_vals["account_id"] = inv_line.account_id.id
                if hasattr(inv_line, "analytic_distribution") and inv_line.analytic_distribution:
                    line_vals["analytic_distribution"] = inv_line.analytic_distribution
            else:
                # If no invoice line, try to get account from product
                accounts = line.product_id.product_tmpl_id.get_product_accounts()
                if accounts.get('expense'):
                    line_vals["account_id"] = accounts['expense'].id
                elif accounts.get('income'):
                    line_vals["account_id"] = accounts['income'].id
                    
            credit_note_lines.append((0, 0, line_vals))

        # Build narraton / reason text
        narration = self.reason or ""

        # Create the credit note
        move_vals = {
            "move_type": "out_refund",
            "partner_id": self.invoice_id.partner_id.id if self.invoice_id else self.sale_id.partner_id.id,
            "invoice_origin": self.sale_id.name,
            "currency_id": self.invoice_id.currency_id.id if self.invoice_id else self.sale_id.currency_id.id,
            "invoice_payment_term_id": False,
            "narration": narration,
            "source_sale_id": self.sale_id.id,
            "invoice_line_ids": credit_note_lines,
        }
        if self.invoice_id:
            move_vals["reversed_entry_id"] = self.invoice_id.id
            
        credit_note = self.env["account.move"].create(move_vals)

        # Return action to open the created credit note
        return {
            "type": "ir.actions.act_window",
            "name": _("Credit Note"),
            "res_model": "account.move",
            "res_id": credit_note.id,
            "view_mode": "form",
            "target": "current",
        }


class SaleOrderCreditNoteWizardLine(models.TransientModel):
    _name = "sale.order.credit.note.wizard.line"
    _description = "Sale Order Credit Note Wizard Line"

    wizard_id = fields.Many2one(
        "sale.order.credit.note.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(string="Select", default=False)
    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Sale Order Line",
        readonly=True,
    )
    invoice_line_id = fields.Many2one(
        "account.move.line",
        string="Invoice Line",
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        readonly=True,
    )
    name = fields.Text(
        string="Description",
        readonly=True,
    )
    invoiced_qty = fields.Float(
        string="Invoiced Qty",
        readonly=True,
        digits="Product Unit of Measure",
    )
    credited_qty = fields.Float(
        string="Already Credited",
        readonly=True,
        digits="Product Unit of Measure",
    )
    refundable_qty = fields.Float(
        string="Refundable Qty",
        readonly=True,
        digits="Product Unit of Measure",
    )
    credit_qty = fields.Float(
        string="Credit Qty",
        digits="Product Unit of Measure",
    )
    price_unit = fields.Float(
        string="Unit Price",
        readonly=True,
        digits="Product Price",
    )
    discount = fields.Float(
        string="Discount (%)",
        readonly=True,
    )
    tax_ids = fields.Many2many(
        "account.tax",
        string="Taxes",
        readonly=True,
    )
