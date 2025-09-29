from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ExpenseSheetBatchBillWizard(models.TransientModel):
    _name = 'hr.expense.sheet.batch.bill.wizard'
    _description = 'Expense Sheet Batch Bill Creation Wizard'

    def _default_sheet_ids(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        if active_model == 'hr.expense.sheet' and active_ids:
            sheets = self.env['hr.expense.sheet'].browse(active_ids)
            # Filter to only sheets that haven't been billed yet and have the right clear_mode
            return sheets.filtered(
                lambda s: not s.is_billed and 
                         s.clear_mode and 
                         s.clear_mode != 'reimburse_employee' and 
                         s.state == 'approve'
            ).ids
        return []

    sheet_ids = fields.Many2many(
        'hr.expense.sheet',
        string='Expense Sheets',
        default=_default_sheet_ids
    )
    sheets_to_process_count = fields.Integer(
        compute='_compute_sheets_to_process_count',
        string='Sheets to Process'
    )
    
    def _compute_sheets_to_process_count(self):
        for wizard in self:
            wizard.sheets_to_process_count = len(wizard.sheet_ids)

    def action_create_bills_batch(self):
        """Create bills for selected expense sheets"""
        if not self.sheet_ids:
            raise UserError(_("No expense sheets selected or no sheets available to process."))
        
        processed_count = 0
        error_logs = []
        
        for sheet in self.sheet_ids:
            try:
                # Check if sheet is already billed
                if sheet.is_billed:
                    error_logs.append(_("Sheet %s is already billed and will be skipped.") % sheet.name)
                    continue
                
                # Check if clear mode is appropriate
                if not sheet.clear_mode or sheet.clear_mode == 'reimburse_employee':
                    error_logs.append(_("Sheet %s has clear mode 'reimburse_employee' and will be skipped.") % sheet.name)
                    continue
                
                # Check if sheet is approved
                if sheet.state != 'approve':
                    error_logs.append(_("Sheet %s is not approved and will be skipped.") % sheet.name)
                    continue
                
                # Create bills for this sheet
                sheet.action_create_vendor_bills()
                processed_count += 1
                
            except Exception as e:
                error_logs.append(_("Error processing sheet %s: %s") % (sheet.name, str(e)))
        
        # Create a message with the results
        message = _("Batch processing completed. Successfully processed %d sheets." % processed_count)
        if error_logs:
            message += _("\n\nError logs:\n") + "\n".join(error_logs)
        
        # Return action with message
        return {
            'type': 'ir.actions.act_window',
            'name': _('Batch Processing Results'),
            'res_model': 'ir.actions.act_window',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_name': message,
            },
            'res_id': False
        }