# -*- coding: utf-8 -*-

import uuid

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('-at_install', 'post_install')
class TestMarginApprovalRule(TransactionCase):
    """Test margin.approval.rule and margin.approval.rule.line models"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rule = cls.env['margin.approval.rule']
        cls.RuleLine = cls.env['margin.approval.rule.line']

        cls.sales_user = cls.env['res.users'].create({
            'name': 'Test Sales User - Margin',
            'login': 'test_sales_margin_%s' % uuid.uuid4().hex[:8],
            'email': 'test_sales_margin@test.com',
            'groups_id': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.env.ref('sales_team.group_sale_salesman').id),
            ],
        })
        cls.approver1 = cls.env['res.users'].create({
            'name': 'Test Approver 1 - Margin',
            'login': 'test_approver1_margin_%s' % uuid.uuid4().hex[:8],
            'email': 'test_approver1_margin@test.com',
            'groups_id': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.env.ref('sales_team.group_sale_salesman').id),
            ],
        })
        cls.approver2 = cls.env['res.users'].create({
            'name': 'Test Approver 2 - Margin',
            'login': 'test_approver2_margin_%s' % uuid.uuid4().hex[:8],
            'email': 'test_approver2_margin@test.com',
            'groups_id': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.env.ref('sales_team.group_sale_salesman').id),
            ],
        })
        cls.company = cls.env.company

    # ---- Rule CRUD ----

    def test_01_create_rule(self):
        """Create a basic margin approval rule"""
        rule = self.Rule.create({
            'name': 'Test Rule - Basic',
            'company_id': self.company.id,
            'user_ids': [(4, self.sales_user.id)],
        })
        self.assertTrue(rule.id)
        self.assertTrue(rule.active)
        self.assertIn(self.sales_user, rule.user_ids)

    def test_02_create_rule_with_lines(self):
        """Create a rule with margin range lines"""
        rule = self.Rule.create({
            'name': 'Test Rule - With Lines',
            'company_id': self.company.id,
            'user_ids': [(4, self.sales_user.id)],
        })
        line1 = self.RuleLine.create({
            'rule_id': rule.id,
            'min_margin': 0,
            'max_margin': 10,
            'approver_ids': [(4, self.approver1.id)],
            'approval_type': 'any',
        })
        line2 = self.RuleLine.create({
            'rule_id': rule.id,
            'min_margin': 10.01,
            'max_margin': 20,
            'approver_ids': [(4, self.approver1.id), (4, self.approver2.id)],
            'approval_type': 'all',
        })
        self.assertEqual(len(rule.line_ids), 2)
        self.assertEqual(line1.approval_type, 'any')
        self.assertEqual(line2.approval_type, 'all')

    # ---- Constraints ----

    def test_03_constraint_min_max_margin(self):
        """min_margin > max_margin should raise ValidationError"""
        rule = self.Rule.create({
            'name': 'Test Rule - Constraint MinMax',
            'company_id': self.company.id,
        })
        with self.assertRaises(ValidationError):
            self.RuleLine.create({
                'rule_id': rule.id,
                'min_margin': 20,
                'max_margin': 10,
                'approver_ids': [(4, self.approver1.id)],
            })

    def test_04_constraint_overlapping_ranges(self):
        """Overlapping margin ranges in same rule should raise ValidationError"""
        rule = self.Rule.create({
            'name': 'Test Rule - Overlap',
            'company_id': self.company.id,
        })
        self.RuleLine.create({
            'rule_id': rule.id,
            'min_margin': 0,
            'max_margin': 15,
            'approver_ids': [(4, self.approver1.id)],
        })
        with self.assertRaises(ValidationError):
            self.RuleLine.create({
                'rule_id': rule.id,
                'min_margin': 10,
                'max_margin': 25,
                'approver_ids': [(4, self.approver2.id)],
            })

    def test_05_constraint_unique_user_per_company(self):
        """A user can only belong to one active rule per company"""
        self.Rule.create({
            'name': 'Test Rule - Unique 1',
            'company_id': self.company.id,
            'user_ids': [(4, self.sales_user.id)],
        })
        with self.assertRaises(ValidationError):
            self.Rule.create({
                'name': 'Test Rule - Unique 2',
                'company_id': self.company.id,
                'user_ids': [(4, self.sales_user.id)],
            })

    def test_06_inactive_rule_allows_duplicate_user(self):
        """Inactive rule should not block user from being in another rule"""
        self.Rule.create({
            'name': 'Test Rule - Inactive',
            'company_id': self.company.id,
            'user_ids': [(4, self.sales_user.id)],
            'active': False,
        })
        rule2 = self.Rule.create({
            'name': 'Test Rule - Active After Inactive',
            'company_id': self.company.id,
            'user_ids': [(4, self.sales_user.id)],
        })
        self.assertTrue(rule2.active)

    # ---- get_applicable_rule_for_user ----

    def test_07_get_applicable_rule(self):
        """get_applicable_rule_for_user returns correct rule"""
        rule = self.Rule.create({
            'name': 'Test Rule - Lookup',
            'company_id': self.company.id,
            'user_ids': [(4, self.sales_user.id)],
        })
        found = self.Rule.get_applicable_rule_for_user(self.sales_user.id, self.company.id)
        self.assertEqual(found, rule)

    def test_08_get_applicable_rule_no_match(self):
        """get_applicable_rule_for_user returns empty for unmatched user"""
        other_user = self.env['res.users'].create({
            'name': 'Test Other User - Margin',
            'login': 'test_other_margin_%s' % uuid.uuid4().hex[:8],
            'email': 'test_other_margin@test.com',
        })
        found = self.Rule.get_applicable_rule_for_user(other_user.id, self.company.id)
        self.assertFalse(found)

    # ---- get_applicable_line ----

    def test_09_get_applicable_line(self):
        """get_applicable_line finds the correct margin range"""
        rule = self.Rule.create({
            'name': 'Test Rule - Line Lookup',
            'company_id': self.company.id,
        })
        line1 = self.RuleLine.create({
            'rule_id': rule.id,
            'min_margin': 0,
            'max_margin': 10,
            'approver_ids': [(4, self.approver1.id)],
        })
        line2 = self.RuleLine.create({
            'rule_id': rule.id,
            'min_margin': 10.01,
            'max_margin': 25,
            'approver_ids': [(4, self.approver2.id)],
        })
        found = line1.get_applicable_line(5.0)
        self.assertEqual(found, line1)

        found = line1.get_applicable_line(15.0)
        self.assertEqual(found, line2)

        # Outside all ranges
        found = line1.get_applicable_line(30.0)
        self.assertFalse(found)

    # ---- name_get ----

    def test_10_rule_line_name_get(self):
        """name_get shows margin range and approver names"""
        rule = self.Rule.create({
            'name': 'Test Rule - NameGet',
            'company_id': self.company.id,
        })
        line = self.RuleLine.create({
            'rule_id': rule.id,
            'min_margin': 5,
            'max_margin': 15,
            'approver_ids': [(4, self.approver1.id)],
        })
        name = line.name_get()[0][1]
        self.assertIn('5.0% - 15.0%', name)
        self.assertIn(self.approver1.name, name)
