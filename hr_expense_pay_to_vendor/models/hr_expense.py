# Copyright 2021 Ecosoft
# Copyright 2024 Buz
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrExpense(models.Model):
    _inherit = "hr.expense"

    # Temporarily disabled vendor functionality
    # vendor_id = fields.Many2one(
    #     comodel_name="res.partner",
    #     string="To Vendor",
    #     help="Paid by company direct to this vendor",
    # )

    # Temporarily disabled vendor account destination
    # def _get_expense_account_destination(self):
    #     self.ensure_one()
    #     if not (self.payment_mode == "company_account" and self.vendor_id):
    #         return super()._get_expense_account_destination()
    #     # Use vendor's account
    #     account_dest = (
    #         self.vendor_id.property_account_payable_id.id
    #         or self.vendor_id.parent_id.property_account_payable_id.id
    #     )
    #     return account_dest


class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    # Temporarily disabled vendor functionality
    # vendor_id = fields.Many2one(
    #     comodel_name="res.partner",
    #     related="expense_line_ids.vendor_id",
    #     string="To Vendor",
    #     readonly=True,
    # )
    
    is_auto_mode = fields.Boolean(
        string="Auto Mode",
        compute="_compute_auto_mode",
        help="Indicates if this sheet will use AUTO mode (separate bills by vendor)"
    )
    
    vendor_summary = fields.Text(
        string="Vendor Summary", 
        compute="_compute_vendor_summary",
        help="Summary of vendors in this expense sheet"
    )
    
    # Temporarily disabled vendor compute methods
    # @api.depends("expense_line_ids.vendor_id")
    def _compute_auto_mode(self):
        for sheet in self:
            sheet.is_auto_mode = False  # Disabled AUTO mode temporarily
    
    # @api.depends("expense_line_ids.vendor_id")  
    def _compute_vendor_summary(self):
        for sheet in self:
            sheet.vendor_summary = ""  # Disabled vendor summary temporarily
            
            sheet.vendor_summary = "\n".join(summary_lines)

    @api.constrains("expense_line_ids")
    def _check_payment_mode(self):
        res = super()._check_payment_mode()
        for sheet in self:
            expenses = sheet.expense_line_ids
            payment_mode = expenses.mapped("payment_mode")
            if payment_mode and payment_mode[0] == "company_account":
                # Check if this is AUTO mode (has advance clearing or mixed vendor scenario)
                is_auto_mode = (
                    (hasattr(sheet, 'advance_clearing_type') and sheet.advance_clearing_type != 'none') or
                    len(set(exp.vendor_id.id if exp.vendor_id else None for exp in expenses)) > 1
                )
                
                # Temporarily disabled vendor validation
                pass
        return res

    def action_sheet_move_create(self):
        # Temporarily disabled AUTO mode functionality
        res = super().action_sheet_move_create()
        return res
    
    def _create_auto_mode_entries(self, sheet):
        """Create separate vendor bills for AUTO mode with mixed vendors"""
        # Group expenses by vendor
        vendor_groups = {}
        for expense in sheet.expense_line_ids:
            vendor_key = expense.vendor_id.id if expense.vendor_id else 'no_vendor'
            if vendor_key not in vendor_groups:
                vendor_groups[vendor_key] = []
            vendor_groups[vendor_key].append(expense)
        
        bill_ids = []
        
        # Create separate vendor bills for each vendor group
        for vendor_key, expenses in vendor_groups.items():
            if vendor_key == 'no_vendor':
                # For employees without vendor, create expense reimbursement (standard flow)
                # Create temporary sheet for employee reimbursement
                temp_sheet = sheet.copy({
                    'name': f"{sheet.name} - Employee Reimbursement",
                    'expense_line_ids': [(6, 0, [e.id for e in expenses])],
                })
                
                # Move expenses to temp sheet temporarily
                for expense in expenses:
                    expense.sheet_id = temp_sheet.id
                
                # Process standard expense flow
                temp_sheet.action_submit_sheet()
                temp_sheet.approve_expense_sheets() 
                temp_sheet.action_sheet_move_create()
                
                if temp_sheet.account_move_ids:
                    bill_ids.extend(temp_sheet.account_move_ids.ids)
                
                # Move expenses back
                for expense in expenses:
                    expense.sheet_id = sheet.id
                    
                temp_sheet.unlink()
                
            else:
                # For vendors, create vendor bill
                vendor = self.env['res.partner'].browse(vendor_key)
                
                # Get vendor journal (purchase journal)
                vendor_journal = self.env['account.journal'].search([
                    ('type', '=', 'purchase'),
                    ('company_id', '=', sheet.company_id.id)
                ], limit=1)
                
                if not vendor_journal:
                    vendor_journal = sheet.journal_id
                
                # Prepare vendor bill
                bill_vals = {
                    'move_type': 'in_invoice',
                    'partner_id': vendor.id,
                    'journal_id': vendor_journal.id,
                    'ref': f"{sheet.name} - {vendor.name}",
                    'invoice_date': fields.Date.context_today(self),
                    'company_id': sheet.company_id.id,
                    'currency_id': sheet.currency_id.id,
                    'invoice_line_ids': [],
                }
                
                # Add invoice lines for each expense
                for expense in expenses:
                    line_vals = {
                        'name': expense.name,
                        'product_id': expense.product_id.id if expense.product_id else False,
                        'quantity': 1,
                        'price_unit': expense.total_amount,
                        'account_id': expense.account_id.id,
                        'tax_ids': [(6, 0, expense.tax_ids.ids)] if expense.tax_ids else False,
                    }
                    
                    # Add analytic distribution if available
                    if expense.analytic_distribution:
                        line_vals['analytic_distribution'] = expense.analytic_distribution
                        
                    bill_vals['invoice_line_ids'].append((0, 0, line_vals))
                
                # Create vendor bill
                vendor_bill = self.env['account.move'].create(bill_vals)
                
                # Auto-confirm the bill if needed
                if vendor_bill.state == 'draft':
                    vendor_bill.action_post()
                
                bill_ids.append(vendor_bill.id)
        
        # Link all bills to original sheet and update state
        if bill_ids:
            sheet.account_move_ids = [(6, 0, bill_ids)]
            sheet.state = 'post'
            
            return {
                'type': 'ir.actions.act_window',
                'name': _('Vendor Bills'),
                'res_model': 'account.move',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', bill_ids)],
                'target': 'current',
            }
        
        return {'type': 'ir.actions.act_window_close'}

    def _prepare_payment_vals(self):
        self.ensure_one()
        payment_vals = super()._prepare_payment_vals()
        
        if self.payment_mode == "company_account":
            # Check if we need AUTO mode processing (mixed vendors)
            unique_vendors = set(exp.vendor_id.id if exp.vendor_id else None for exp in self.expense_line_ids)
            is_auto_mode = len(unique_vendors) > 1
            
            # For AUTO mode, handle each line individually based on its vendor
            if is_auto_mode:
                # Group expenses by vendor
                expense_vendor_map = {}
                for expense in self.expense_line_ids:
                    vendor_key = expense.vendor_id.id if expense.vendor_id else None
                    expense_vendor_map[expense.id] = vendor_key
                
                # Update journal entry lines with appropriate partners
                for line in payment_vals["line_ids"]:
                    if line[2].get("expense_id"):
                        expense_id = line[2]["expense_id"]
                        vendor_id = expense_vendor_map.get(expense_id)
                        if vendor_id:
                            vendor = self.env['res.partner'].browse(vendor_id)
                            line[2]["partner_id"] = vendor_id
                            # Update name if not a tax line
                            if not line[2].get("tax_base_amount", False):
                                expense_name = line[2]["name"].split(":")
                                if len(expense_name) > 1:
                                    line[2]["name"] = f"{vendor.name}: {expense_name[1].strip()}"
                        # If no vendor, keep employee as partner (default behavior)
                        
            # For single vendor mode (original logic)
            elif self.vendor_id:
                for line in payment_vals["line_ids"]:
                    line[2]["partner_id"] = self.vendor_id.id
                    # Overwrite name without taxes
                    if line[2].get("tax_base_amount", False):
                        continue
                    expense_name = line[2]["name"].split(":")
                    if len(expense_name) > 1:
                        line[2]["name"] = f"{self.vendor_id.name}: {expense_name[1].strip()}"
                    
        return payment_vals
