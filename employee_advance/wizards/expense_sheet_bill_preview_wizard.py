from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ExpenseSheetBillPreviewWizard(models.TransientModel):
    _name = 'hr.expense.sheet.bill.preview.wizard'
    _description = 'Expense Sheet Bill Preview Wizard'

    def _default_sheet_id(self):
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')
        if active_model == 'hr.expense.sheet' and active_id:
            return active_id
        return False

    sheet_id = fields.Many2one(
        'hr.expense.sheet',
        string='Expense Sheet',
        default=_default_sheet_id,
        required=True
    )
    
    preview_line_ids = fields.One2many(
        'hr.expense.sheet.bill.preview.line',
        'wizard_id',
        string='Preview Lines',
        compute='_compute_preview_lines'
    )

    def _compute_preview_lines(self):
        """Compute preview lines showing how bills will be grouped"""
        for wizard in self:
            # Remove existing lines
            wizard.preview_line_ids = [(5, 0, 0)]
            
            if not wizard.sheet_id:
                continue
            
            sheet = wizard.sheet_id
            
            # Group expense lines by (vendor_or_employee_partner, company, currency)
            groups = {}
            
            for expense in sheet.expense_line_ids:
                # Determine the partner based on clear_mode and vendor_id
                partner_id = sheet._get_partner_for_expense(expense)
                
                if not partner_id:
                    continue
                
                # Get partner name
                partner = self.env['res.partner'].browse(partner_id)
                
                # Create group key
                group_key = (
                    partner_id, 
                    expense.company_id.id, 
                    expense.currency_id.id
                )
                
                if group_key not in groups:
                    groups[group_key] = {
                        'partner_id': partner_id,
                        'partner_name': partner.name,
                        'company_id': expense.company_id.id,
                        'company_name': expense.company_id.name,
                        'currency_id': expense.currency_id.id,
                        'currency_name': expense.currency_id.name,
                        'expenses': self.env['hr.expense']
                    }
                
                groups[group_key]['expenses'] |= expense
            
            # Create preview lines
            preview_lines = []
            for idx, (group_key, group_data) in enumerate(groups.items()):
                line_vals = {
                    'wizard_id': wizard.id,
                    'sequence': idx + 1,
                    'partner_name': group_data['partner_name'],
                    'company_name': group_data['company_name'],
                    'currency_name': group_data['currency_name'],
                    'expense_count': len(group_data['expenses']),
                    'total_amount': sum(group_data['expenses'].mapped('total_amount')),
                    'expense_names': ', '.join(group_data['expenses'].mapped('name'))
                }
                preview_lines.append((0, 0, line_vals))
            
            wizard.preview_line_ids = preview_lines

    def action_create_bills_from_preview(self):
        """Create bills based on the preview"""
        if self.sheet_id:
            return self.sheet_id.action_create_vendor_bills()
        return {'type': 'ir.actions.act_window_close'}


class ExpenseSheetBillPreviewLine(models.TransientModel):
    _name = 'hr.expense.sheet.bill.preview.line'
    _description = 'Expense Sheet Bill Preview Line'
    _order = 'sequence'

    wizard_id = fields.Many2one(
        'hr.expense.sheet.bill.preview.wizard',
        string='Wizard',
        ondelete='cascade'
    )
    
    sequence = fields.Integer(string='Sequence')
    
    partner_name = fields.Char(string='Partner')
    
    company_name = fields.Char(string='Company')
    
    currency_name = fields.Char(string='Currency')
    
    expense_count = fields.Integer(string='Expense Count')
    
    total_amount = fields.Float(string='Total Amount')
    
    expense_names = fields.Text(string='Expense Names')