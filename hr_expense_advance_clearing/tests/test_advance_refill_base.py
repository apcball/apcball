import odoo
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo import fields


@tagged('extension', 'at_install')
class TestAdvanceRefillBase(TransactionCase):

    def setUp(self):
        super().setUp()
        
        # Common setup for tests
        self.Employee = self.env['hr.employee']
        self.AdvanceBox = self.env['employee.advance.box']
        self.AccountAccount = self.env['account.account']
        self.AccountJournal = self.env['account.journal']
        self.AccountMove = self.env['account.move']
        self.ResUsers = self.env['res.users']
        self.AdvanceRefillWizard = self.env['advance.refill.base.wizard']
        
        # Create test user
        self.test_user = self.ResUsers.create({
            'name': 'Test Advance User',
            'login': 'test_adv_user',
            'email': 'test_adv_user@example.com',
        })
        
        # Create test employee with user partner
        self.test_employee = self.Employee.create({
            'name': 'Test Employee',
            'user_id': self.test_user.id
        })
        
        # Get company
        self.company = self.env.company

        # Create advance account (141101)
        self.advance_account = self.AccountAccount.create({
            'name': 'Employee Advances',
            'code': '141101',
            'account_type': 'asset_current',
            'company_id': self.company.id,
        })

        # Create bank journal
        self.bank_journal = self.AccountJournal.create({
            'name': 'Bank Journal',
            'code': 'BNK6',
            'type': 'bank',
            'company_id': self.company.id,
            'default_account_id': self.env['account.account'].search([
                ('account_type', '=', 'asset_cash'),
                ('company_id', '=', self.company.id)
            ], limit=1).id or self.env['account.account'].create({
                'name': 'Default Bank Account',
                'code': '101001',
                'account_type': 'asset_cash',
                'company_id': self.company.id,
            }).id
        })

        # Create advance box
        self.advance_box = self.AdvanceBox.create({
            'employee_id': self.test_employee.id,
            'account_id': self.advance_account.id,
            'journal_id': self.bank_journal.id,
        })
        
    def test_remember_base_amount_field_exists(self):
        """Test that remember_base_amount field exists on advance box"""
        self.assertTrue(hasattr(self.advance_box, 'remember_base_amount'))
        # Initially should be 0
        self.assertEqual(self.advance_box.remember_base_amount, 0.0)
        
    def test_refill_wizard_initialization(self):
        """Test the refill base wizard initialization"""
        wizard = self.AdvanceRefillWizard.with_context(
            active_id=self.advance_box.id,
            active_model='employee.advance.box'
        ).create({})
        
        self.assertEqual(wizard.employee_id.id, self.test_employee.id)
        self.assertEqual(wizard.box_id.id, self.advance_box.id)
        self.assertEqual(wizard.current_balance, 0.0)  # Initial balance is 0
        self.assertEqual(wizard.base_amount_ref, 0.0)  # Initial base amount is 0
        self.assertEqual(wizard.manual_base_amount, 0.0)  # Initial manual base is 0
        
        # Should need initial base amount when base is 0
        self.assertTrue(wizard.need_initial_base)
        
    def test_refill_wizard_with_existing_base(self):
        """Test the refill wizard when base amount already exists"""
        # Set an existing base amount
        self.advance_box.remember_base_amount = 10000.0
        
        wizard = self.AdvanceRefillWizard.with_context(
            active_id=self.advance_box.id,
            active_model='employee.advance.box'
        ).create({})
        
        self.assertFalse(wizard.need_initial_base)
        self.assertEqual(wizard.base_amount_ref, 10000.0)
        self.assertEqual(wizard.manual_base_amount, 10000.0)  # Should default to base amount
        
    def test_topup_calculation(self):
        """Test that topup amount is calculated correctly"""
        # Set base amount to 10000
        self.advance_box.remember_base_amount = 10000.0
        
        wizard = self.AdvanceRefillWizard.with_context(
            active_id=self.advance_box.id,
            active_model='employee.advance.box'
        ).create({
            'initial_base_amount': 10000.0,
        })
        
        # With 0 balance and 10000 base, topup should be 10000
        wizard._onchange_calculate_topup()
        self.assertEqual(wizard.topup_amount, 10000.0)
        
    def test_manual_base_amount_calculation(self):
        """Test that topup is calculated using manual base amount"""
        # Create a journal entry to simulate balance of 6000
        partner = self.test_employee.user_partner_id
        move_vals = {
            'journal_id': self.bank_journal.id,
            'date': fields.Date.context_today(self.advance_box),
            'line_ids': [
                (0, 0, {
                    'account_id': self.advance_account.id,
                    'partner_id': partner.id,
                    'debit': 6000.0,
                    'credit': 0,
                }),
                (0, 0, {
                    'account_id': self.bank_journal.default_account_id.id,
                    'debit': 0,
                    'credit': 6000.0,
                }),
            ]
        }
        move = self.AccountMove.create(move_vals)
        move.action_post()
        
        # Now balance should be 6000
        self.assertEqual(self.advance_box.balance, 6000.0)
        
        # Set base to 10000
        self.advance_box.remember_base_amount = 10000.0
        
        wizard = self.AdvanceRefillWizard.with_context(
            active_id=self.advance_box.id,
            active_model='employee.advance.box'
        ).create({})
        
        # Change the manual base amount to 12000
        wizard.manual_base_amount = 12000.0
        wizard._onchange_calculate_topup()
        # Since manual base (12000) - balance (6000) = 6000, topup should be 6000
        self.assertEqual(wizard.topup_amount, 6000.0)
        
    def test_no_refill_needed(self):
        """Test scenario where no refill is needed"""
        # Create a journal entry to simulate balance of 10000
        partner = self.test_employee.user_partner_id
        move_vals = {
            'journal_id': self.bank_journal.id,
            'date': fields.Date.context_today(self.advance_box),
            'line_ids': [
                (0, 0, {
                    'account_id': self.advance_account.id,
                    'partner_id': partner.id,
                    'debit': 10000.0,
                    'credit': 0,
                }),
                (0, 0, {
                    'account_id': self.bank_journal.default_account_id.id,
                    'debit': 0,
                    'credit': 10000.0,
                }),
            ]
        }
        move = self.AccountMove.create(move_vals)
        move.action_post()
        
        # Now balance should be 10000
        self.assertEqual(self.advance_box.balance, 10000.0)
        
        # Set base to 10000
        self.advance_box.remember_base_amount = 10000.0
        
        wizard = self.AdvanceRefillWizard.with_context(
            active_id=self.advance_box.id,
            active_model='employee.advance.box'
        ).create({})
        
        wizard._onchange_calculate_topup()
        # Since balance equals base, topup should be 0
        self.assertEqual(wizard.topup_amount, 0.0)
        
    def test_refill_with_existing_balance_less_than_base(self):
        """Test refill when current balance is less than base"""
        # Create a journal entry to simulate balance of 6000
        partner = self.test_employee.user_partner_id
        move_vals = {
            'journal_id': self.bank_journal.id,
            'date': fields.Date.context_today(self.advance_box),
            'line_ids': [
                (0, 0, {
                    'account_id': self.advance_account.id,
                    'partner_id': partner.id,
                    'debit': 6000.0,
                    'credit': 0,
                }),
                (0, 0, {
                    'account_id': self.bank_journal.default_account_id.id,
                    'debit': 0,
                    'credit': 6000.0,
                }),
            ]
        }
        move = self.AccountMove.create(move_vals)
        move.action_post()
        
        # Now balance should be 6000
        self.assertEqual(self.advance_box.balance, 6000.0)
        
        # Set base to 10000
        self.advance_box.remember_base_amount = 10000.0
        
        wizard = self.AdvanceRefillWizard.with_context(
            active_id=self.advance_box.id,
            active_model='employee.advance.box'
        ).create({})
        
        wizard._onchange_calculate_topup()
        # Since base (10000) - balance (6000) = 4000, topup should be 4000
        self.assertEqual(wizard.topup_amount, 4000.0)