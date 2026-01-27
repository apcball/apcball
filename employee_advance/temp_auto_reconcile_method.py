    def _auto_reconcile_wht_entries(self):
        """Auto reconcile WHT entries based on base amount excluding VAT"""
        self.ensure_one()
        
        if self.move_type != 'entry' or not self.line_ids:
            return False
        
        # Look for WHT lines in this journal entry
        wht_lines = self.line_ids.filtered(lambda l: l.tax_line_id and l.tax_line_id.amount < 0)
        
        if not wht_lines:
            # If no WHT tax lines, try to find lines that have WHT-related accounts
            wht_accounts = self.env['account.account'].search([
                ('name', 'ilike', '%withholding%'),
                ('company_id', '=', self.company_id.id)
            ])
            wht_lines = self.line_ids.filtered(lambda l: l.account_id in wht_accounts)
        
        if not wht_lines:
            return False
        
        # For each WHT line, try to find corresponding payable/receivable entries to reconcile
        reconciled_count = 0
        for wht_line in wht_lines:
            # Find payable lines with the same partner to reconcile against the WHT
            related_payable_lines = self.line_ids.filtered(
                lambda l: (l.partner_id.id == wht_line.partner_id.id and 
                          l.account_id.account_type == 'liability_payable' and 
                          l.id != wht_line.id)
            )
            
            for payable_line in related_payable_lines:
                try:
                    # For WHT, we typically reconcile the liability reduction (the payable line)
                    # against the payment or other journal entry lines
                    lines_to_reconcile = payable_line + wht_line
                    if lines_to_reconcile and len(lines_to_reconcile.mapped('account_id')) == 1:
                        lines_to_reconcile.reconcile()
                        reconciled_count += 1
                        _logger.info(f"WHT auto-reconciliation successful for lines in move {self.name}")
                        break  # Don't try to reconcile the same WHT line multiple times
                except Exception as e:
                    _logger.warning(f"Could not reconcile WHT line {wht_line.id} with payable {payable_line.id}: {str(e)}")
        
        return True