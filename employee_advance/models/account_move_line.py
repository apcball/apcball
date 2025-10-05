from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _invalidate_advance_box_balance(self, account, partner):
        """Trigger balance recompute for advance boxes affected by this account/partner"""
        if not account:
            return

        partner_id = partner.id if hasattr(partner, 'id') else partner
        advance_boxes = self.env['employee.advance.box'].search([
            ('account_id', '=', account.id)
        ])
        for box in advance_boxes:
            # Check if the partner matches the employee's partner
            box_partner = box._get_employee_partner()
            if box_partner and box_partner == partner_id:
                # Trigger recompute of the balance
                box._refresh_balance_simple()

    def create(self, vals_list):
        """Override create to update advance box balance when relevant lines are created"""
        records = super(AccountMoveLine, self).create(vals_list)
        for record in records:
            if record.account_id and record.partner_id:
                self._invalidate_advance_box_balance(record.account_id, record.partner_id)
        return records

    def write(self, vals):
        """Override write to update advance box balance when relevant lines are updated"""
        # Capture old account/partner values per record before write
        old_values = [(line, line.account_id, line.partner_id) for line in self]
        result = super(AccountMoveLine, self).write(vals)

        # After write, invalidate for both old and new values for each record
        for line, old_account, old_partner in old_values:
            # Invalidate for old values
            self._invalidate_advance_box_balance(old_account, old_partner)
            # Invalidate for new values
            self._invalidate_advance_box_balance(line.account_id, line.partner_id)

        return result

    def unlink(self):
        """Override unlink to update advance box balance when relevant lines are deleted"""
        # Store the records affected before deletion
        lines_to_check = list(self)
        old_values = [(line.account_id, line.partner_id) for line in lines_to_check]

        result = super(AccountMoveLine, self).unlink()

        # Update balances for affected advance boxes using stored old values
        for old_account, old_partner in old_values:
            self._invalidate_advance_box_balance(old_account, old_partner)

        return result