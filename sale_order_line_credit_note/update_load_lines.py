import re

with open('wizard/sale_order_credit_note_wizard.py', 'r') as f:
    content = f.read()

old_load = '''    def _load_lines(self):
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
            
        self.line_ids = lines_vals'''

content = content.replace(old_load, new_load)

with open('wizard/sale_order_credit_note_wizard.py', 'w') as f:
    f.write(content)

