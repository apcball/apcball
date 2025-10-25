# -*- coding: utf-8 -*-

from odoo.tests import common, TransactionCase
from odoo.exceptions import ValidationError


class TestIssueFields(TransactionCase):
    """Test the new Issue ticket fields functionality"""
    
    def setUp(self):
        super(TestIssueFields, self).setUp()
        
        # Create test employee
        self.employee = self.env['hr.employee'].create({
            'name': 'Test Employee',
            'work_email': 'test.employee@example.com',
        })
        
        # Create test IT responsible user
        self.it_user = self.env['res.users'].create({
            'name': 'IT Support',
            'login': 'it_support',
            'email': 'it.support@example.com',
        })
        
    def test_issue_ticket_with_required_fields(self):
        """Test creating Issue ticket with all required fields"""
        ticket = self.env['it.ticket'].create({
            'category': 'issue',
            'employee_id': self.employee.id,
            'requester_email': 'test@example.com',
            'line_id': 'testline123',
            'symptoms': 'Computer is running slow',
            'computer_name': 'PC-TEST-001',
            'description': 'Test issue description',
        })
        
        self.assertEqual(ticket.category, 'issue')
        self.assertEqual(ticket.requester_email, 'test@example.com')
        self.assertEqual(ticket.line_id, 'testline123')
        self.assertEqual(ticket.symptoms, 'Computer is running slow')
        self.assertEqual(ticket.computer_name, 'PC-TEST-001')
        
    def test_issue_ticket_missing_required_fields(self):
        """Test that Issue ticket requires all new fields"""
        with self.assertRaises(ValidationError):
            self.env['it.ticket'].create({
                'category': 'issue',
                'employee_id': self.employee.id,
                'description': 'Test issue description',
                # Missing required fields
            })
            
    def test_access_purchase_ticket_no_required_fields(self):
        """Test that Access and Purchase tickets don't require new fields"""
        # Test Access ticket
        access_ticket = self.env['it.ticket'].create({
            'category': 'access',
            'employee_id': self.employee.id,
            'description': 'Test access request',
        })
        self.assertEqual(access_ticket.category, 'access')
        
        # Test Purchase ticket
        purchase_ticket = self.env['it.ticket'].create({
            'category': 'purchase',
            'employee_id': self.employee.id,
            'description': 'Test purchase request',
        })
        self.assertEqual(purchase_ticket.category, 'purchase')
        
    def test_default_email_from_employee(self):
        """Test that email defaults from employee work email"""
        ticket = self.env['it.ticket'].create({
            'category': 'issue',
            'employee_id': self.employee.id,
            'line_id': 'testline123',
            'symptoms': 'Test symptoms',
            'computer_name': 'PC-TEST-001',
            'description': 'Test issue description',
        })
        
        # Should default to employee work email
        self.assertEqual(ticket.requester_email, 'test.employee@example.com')
        
    def test_issue_workflow_with_new_fields(self):
        """Test that Issue workflow works with new fields"""
        ticket = self.env['it.ticket'].create({
            'category': 'issue',
            'employee_id': self.employee.id,
            'requester_email': 'test@example.com',
            'line_id': 'testline123',
            'symptoms': 'Computer is running slow',
            'computer_name': 'PC-TEST-001',
            'description': 'Test issue description',
            'it_responsible_id': self.it_user.id,
        })
        
        # Test submit workflow
        ticket.action_issue_submit()
        self.assertEqual(ticket.state, 'submitted')
        
        # Test start work workflow
        ticket.action_issue_start_work()
        self.assertEqual(ticket.state, 'in_progress')
        
        # Test resolve workflow
        ticket.action_issue_resolve()
        self.assertEqual(ticket.state, 'resolved')
        
        # Test close workflow
        ticket.action_issue_close()
        self.assertEqual(ticket.state, 'closed')