import re

with open('wizard/sale_order_credit_note_wizard.py', 'r') as f:
    content = f.read()

# Make invoice_id not required
content = content.replace('required=True,\n        domain="[(\'move_type\', \'=\', \'out_invoice\')', 'required=False,\n        domain="[(\'move_type\', \'=\', \'out_invoice\')')

# Rename _load_invoice_lines to _load_lines
content = content.replace('self._load_invoice_lines()', 'self._load_lines()')

# Replace _load_invoice_lines definition
old_load = '''    def _load_invoice_lines(self):
        """Populate wizard lines from the selected invoice."""
        self.line_ids = [(5, 0, 0)]  # clear existing
        if not self.invoice_id:
            return
        sale_lines = self.sale_id.order_line
        lines_vals = []
        for inv_line in self.invoice_id.invoice_line_ids:
            # Skip display lines, sections, notes, lines without product
            if inv_line.display_type or not inv_line.product_id:
                continue
            # Only include lines linked to sale order lines
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
        self.line_ids = lines_vals'''

new_load = '''    def _load_lines(self):
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
        else:
            # Handle negative SO lines directly
            for sl in self.sale_id.order_line:
                if sl.display_type or not sl.product_id:
                    continue
                if sl.product_uom_qty >= 0:
                    continue
                
                # For negative lines, qty is negative.
                # If product_uom_qty is -5, and qty_invoiced is -2, remaining to credit is -3.
                # We show these as positive values in the wizard.
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
                
        self.line_ids = lines_vals'''

content = content.replace(old_load, new_load)

# Fix action_create_credit_note to handle missing invoice_line_id
action_old = '''            if line.invoice_line_id.move_id != self.invoice_id:
                raise UserError(
                    _("Line '%s' does not belong to the selected invoice.") % line.name
                )

        # Build credit note lines
        credit_note_lines = []
        for line in selected_lines:
            inv_line = line.invoice_line_id
            line_vals = {
                "product_id": inv_line.product_id.id,
                "name": inv_line.name,
                "quantity": line.credit_qty,
                "price_unit": inv_line.price_unit,
                "discount": inv_line.discount,
                "tax_ids": [(6, 0, inv_line.tax_ids.ids)],
                "sale_line_ids": [(6, 0, inv_line.sale_line_ids.ids)],
                "source_sale_line_id": line.sale_line_id.id,
                "source_invoice_line_id": inv_line.id,
            }
            # Copy account_id from original invoice line
            if inv_line.account_id:
                line_vals["account_id"] = inv_line.account_id.id
            # Copy analytic distribution if available (Odoo 16+/17)
            if hasattr(inv_line, "analytic_distribution") and inv_line.analytic_distribution:
                line_vals["analytic_distribution"] = inv_line.analytic_distribution
            credit_note_lines.append((0, 0, line_vals))'''

action_new = '''            if line.invoice_line_id and line.invoice_line_id.move_id != self.invoice_id:
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
                    
            credit_note_lines.append((0, 0, line_vals))'''

content = content.replace(action_old, action_new)

# Fix credit note creation to not require reversed_entry_id if no invoice
create_old = '''        # Create the credit note
        credit_note = self.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": self.invoice_id.partner_id.id,
            "invoice_origin": self.sale_id.name,
            "reversed_entry_id": self.invoice_id.id,
            "currency_id": self.invoice_id.currency_id.id,
            "invoice_payment_term_id": False,
            "narration": narration,
            "source_sale_id": self.sale_id.id,
            "invoice_line_ids": credit_note_lines,
        })'''

create_new = '''        # Create the credit note
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
            
        credit_note = self.env["account.move"].create(move_vals)'''

content = content.replace(create_old, create_new)

with open('wizard/sale_order_credit_note_wizard.py', 'w') as f:
    f.write(content)
