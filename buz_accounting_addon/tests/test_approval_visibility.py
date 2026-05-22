import unittest
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.exceptions import UserError

@tagged('post_install', '-at_install')
@unittest.skip("Approval flow (prepared/checked1/checked2/approved) not yet implemented")
class TestApprovalVisibility(TransactionCase):

    def setUp(self):
        super(TestApprovalVisibility, self).setUp()
        
        # Create Users
        self.user_checker1 = new_test_user(self.env, login='checker1', name='Checker 1', groups='account.group_account_user')
        self.user_checker2 = new_test_user(self.env, login='checker2', name='Checker 2', groups='account.group_account_user')
        self.user_approver = new_test_user(self.env, login='approver', name='Approver', groups='account.group_account_user')
        self.user_other = new_test_user(self.env, login='other', name='Other User', groups='account.group_account_user')
        
        # Configure Company Settings
        self.env.company.write({
            'payment_voucher_checker1_id': self.user_checker1.id,
            'payment_voucher_checker2_id': self.user_checker2.id,
            'payment_voucher_approver_id': self.user_approver.id,
        })
        
        # Create a Vendor
        self.vendor = self.env['res.partner'].create({'name': 'Test Vendor', 'supplier_rank': 1})
        
        # Create a Voucher (as admin/superuser initially)
        self.voucher = self.env['account.payment.voucher'].create({
            'partner_id': self.vendor.id,
            'date': '2023-01-01',
            'state': 'draft',  # Start as draft
        })

    def test_visibility_logic(self):
        """Test that only configured users see their respective buttons"""
        
        # 1. State: Draft -> Prepared
        self.voucher.action_confirm()
        self.assertEqual(self.voucher.state, 'prepared')
        
        # 2. Check Visibility for Checker 1 Step
        # Switch to Checker 1
        voucher_as_checker1 = self.voucher.with_user(self.user_checker1)
        voucher_as_checker1._compute_user_visibility() # Force recompute for test environment if needed
        self.assertTrue(voucher_as_checker1.is_current_user_checker1, "Checker 1 should be recognized")
        
        # Switch to Other User
        voucher_as_other = self.voucher.with_user(self.user_other)
        voucher_as_other._compute_user_visibility()
        self.assertFalse(voucher_as_other.is_current_user_checker1, "Other user should NOT be recognized as Checker 1")
        
        # Execute Check 1 as Checker 1
        voucher_as_checker1.action_check1()
        self.assertEqual(self.voucher.state, 'checked1')
        
        # 3. Check Visibility for Checker 2 Step
        # Switch to Checker 2
        voucher_as_checker2 = self.voucher.with_user(self.user_checker2)
        voucher_as_checker2._compute_user_visibility()
        self.assertTrue(voucher_as_checker2.is_current_user_checker2, "Checker 2 should be recognized")
        
        # Switch to Checker 1 (should NOT see button 2)
        voucher_as_checker1._compute_user_visibility()
        self.assertFalse(voucher_as_checker1.is_current_user_checker2, "Checker 1 should NOT be recognized as Checker 2")
        
        # Execute Check 2 as Checker 2
        voucher_as_checker2.action_check2()
        self.assertEqual(self.voucher.state, 'checked2')
        
        # 4. Check Visibility for Approver Step
        # Switch to Approver
        voucher_as_approver = self.voucher.with_user(self.user_approver)
        voucher_as_approver._compute_user_visibility()
        self.assertTrue(voucher_as_approver.is_current_user_approver, "Approver should be recognized")
        
        # Switch to Checker 2 (should NOT see approval button)
        voucher_as_checker2._compute_user_visibility()
        self.assertFalse(voucher_as_checker2.is_current_user_approver, "Checker 2 should NOT be recognized as Approver")
        
        # Execute Approve as Approver
        voucher_as_approver.action_approve()
        self.assertEqual(self.voucher.state, 'approved')

    def test_fallback_logic(self):
        """Test that if NO user is configured, EVERYONE can approve"""
        
        # Clear Company Settings
        self.env.company.write({
            'payment_voucher_checker1_id': False,
            'payment_voucher_checker2_id': False,
            'payment_voucher_approver_id': False,
        })
        
        voucher_as_other = self.voucher.with_user(self.user_other)
        voucher_as_other.action_confirm() # to prepared
        
        # Check 1
        voucher_as_other._compute_user_visibility()
        self.assertTrue(voucher_as_other.is_current_user_checker1, "Should fall back to True if no checker configured")
        voucher_as_other.action_check1()
        
        # Check 2
        voucher_as_other._compute_user_visibility()
        self.assertTrue(voucher_as_other.is_current_user_checker2, "Should fall back to True if no checker configured")
        voucher_as_other.action_check2()
        
        # Approve
        voucher_as_other._compute_user_visibility()
        self.assertTrue(voucher_as_other.is_current_user_approver, "Should fall back to True if no approver configured")
        voucher_as_other.action_approve()
        
        self.assertEqual(self.voucher.state, 'approved')
