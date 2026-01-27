"""
Test file for WHT Clear Advance functionality
This file contains basic tests to verify the WHT advance clearing works correctly
"""

from odoo import fields
from odoo.tests import common
from odoo.exceptions import UserError, ValidationError


class TestWHTClearAdvance(common.TransactionCase):
    
    def setUp(self):
        super().setUp()
        
        # Create test data
        self.company = self.env.ref('base.main_company')
        
        # Create employee
        self.employee = self.env['hr.employee'].create({
            'name': 'Test Employee',
            'company_id': self.company.id,
        })
        
        # Create advance account
        self.advance_account = self.env['account.account'].create({
            'name': 'Employee Advance Account',
            'code': '1340',
            'account_type': 'asset_current',
            'company_id': self.company.id,
        })
        
        # Create advance box
        self.advance_box = self.env['employee.advance.box'].create({
            'employee_id': self.employee.id,
            'account_id': self.advance_account.id,
            'company_id': self.company.id,
            'remember_base_amount': 10000.0,
        })
        
        # Create expense sheet
        self.expense_sheet = self.env['hr.expense.sheet'].create({
            'name': 'Test Expense Sheet',
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'use_advance': True,
            'advance_box_id': self.advance_box.id,
        })
        
        # Create a partner for WHT
        self.partner = self.env['res.partner'].create({
            'name': 'Test Vendor',
            'is_company': True,
            'supplier_rank': 1,
        })
        
        # Try to find or create a general journal
        self.journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company.id)
        ], limit=1)
        
        if not self.journal:
            self.journal = self.env['account.journal'].create({
                'name': 'Miscellaneous Operations',
                'code': 'MISC',
                'type': 'general',
                'company_id': self.company.id,
            })

    def test_wht_wizard_creation(self):
        """Test that WHT wizard can be created with correct values"""
        # Approve expense sheet first
        self.expense_sheet.action_submit_sheet()
        self.expense_sheet.action_approve_expense_sheets()
        
        wizard = self.env['wht.clear.advance.wizard'].create({
            'expense_sheet_id': self.expense_sheet.id,
            'employee_id': self.employee.id,
            'advance_box_id': self.advance_box.id,
            'partner_id': self.partner.id,
            'amount_base': 10000.0,
            'clear_amount': 10000.0,
            'journal_id': self.journal.id,
        })
        
        self.assertEqual(wizard.expense_sheet_id, self.expense_sheet)
        self.assertEqual(wizard.employee_id, self.employee)
        self.assertEqual(wizard.advance_box_id, self.advance_box)
        
    def test_validation_constraints(self):
        """Test validation constraints work correctly"""
        wizard_data = {
            'expense_sheet_id': self.expense_sheet.id,
            'employee_id': self.employee.id,
            'advance_box_id': self.advance_box.id,
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
        }
        
        # Test negative clear amount
        with self.assertRaises(ValidationError):
            wizard = self.env['wht.clear.advance.wizard'].create({
                **wizard_data,
                'amount_base': 1000.0,
                'clear_amount': -100.0,
            })
            wizard._check_amounts()
            
        # Test zero base amount
        with self.assertRaises(ValidationError):
            wizard = self.env['wht.clear.advance.wizard'].create({
                **wizard_data,
                'amount_base': 0.0,
                'clear_amount': 1000.0,
            })
            wizard._check_base_amount()

    def test_expense_sheet_wht_button_visibility(self):
        """Test that WHT button is visible when conditions are met"""
        # Initially not visible (not approved)
        self.assertFalse(self.expense_sheet.can_clear_advance_wht)
        
        # Approve expense sheet
        self.expense_sheet.action_submit_sheet()
        self.expense_sheet.action_approve_expense_sheets()
        
        # Should be visible now
        self.assertTrue(self.expense_sheet.can_clear_advance_wht)
        
        # Mark as billed, should not be visible
        self.expense_sheet.is_billed = True
        self.assertFalse(self.expense_sheet.can_clear_advance_wht)

    def test_expense_sheet_open_wht_wizard(self):
        """Test opening WHT wizard from expense sheet"""
        # Approve expense sheet
        self.expense_sheet.action_submit_sheet()
        self.expense_sheet.action_approve_expense_sheets()
        
        # Open wizard
        action = self.expense_sheet.action_open_wht_clear_advance_wizard()
        
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'wht.clear.advance.wizard')
        self.assertEqual(action['target'], 'new')
        
        # Check context
        context = action['context']
        self.assertEqual(context['default_expense_sheet_id'], self.expense_sheet.id)
        self.assertEqual(context['default_employee_id'], self.employee.id)
        self.assertEqual(context['default_advance_box_id'], self.advance_box.id)