from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _invalidate_advance_box_balance(self, account, partner):
        """Trigger balance recompute for advance boxes affected by this account/partner"""
        if account and partner:
            advance_boxes = self.env['employee.advance.box'].search([
                ('account_id', '=', account.id)
            ])
            for box in advance_boxes:
                # Check if the partner matches the employee's partner
                box_partner = box._get_employee_partner()
                if box_partner and box_partner == partner.id:
                    # Trigger recompute of the balance
                    box._trigger_balance_recompute()

    def create(self, vals_list):
        """Override create to update advance box balance when relevant lines are created"""
        records = super(AccountMoveLine, self).create(vals_list)
        for record in records:
            if record.account_id and record.partner_id:
                self._invalidate_advance_box_balance(record.account_id, record.partner_id)
        return records

    def write(self, vals):
        """Override write to update advance box balance when relevant lines are updated"""
        # Store old values before write
        accounts_before = self.account_id
        partners_before = self.partner_id
        result = super(AccountMoveLine, self).write(vals)
        
        # Check if account_id or partner_id changed
        if 'account_id' in vals or 'partner_id' in vals:
            # Invalidate for old values
            for line in self:
                if hasattr(line, 'account_id') and hasattr(line, 'partner_id'):
                    # For old values
                    self._invalidate_advance_box_balance(accounts_before, partners_before)
                    # For new values
                    self._invalidate_advance_box_balance(line.account_id, line.partner_id)
        else:
            # Values didn't change, just invalidate for current values
            for line in self:
                self._invalidate_advance_box_balance(line.account_id, line.partner_id)
        return result

    def unlink(self):
        """Override unlink to update advance box balance when relevant lines are deleted"""
        # Store the records affected before deletion
        lines_to_check = self.filtered(
            lambda line: line.account_id and line.partner_id
        )
        # Store account and partner before deletion
        old_accounts = [line.account_id for line in lines_to_check]
        old_partners = [line.partner_id for line in lines_to_check]
        
        result = super(AccountMoveLine, self).unlink()
        
        # Update balances for affected advance boxes
        for i, line in enumerate(lines_to_check):
            self._invalidate_advance_box_balance(old_accounts[i], old_partners[i])
        return result