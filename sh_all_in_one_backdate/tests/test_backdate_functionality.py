# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, AccessError
from datetime import datetime, timedelta
from odoo import fields


class TestBackdateFunctionality(TransactionCase):

    def setUp(self):
        super().setUp()
        
        # Create test users
        self.backdate_user = self.env['res.users'].create({
            'name': 'Backdate User',
            'login': 'backdate_user',
            'email': 'backdate_user@test.com',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('sh_all_in_one_backdate.group_backdate_user').id,
            ])]
        })
        
        self.backdate_manager = self.env['res.users'].create({
            'name': 'Backdate Manager',
            'login': 'backdate_manager',
            'email': 'backdate_manager@test.com',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('sh_all_in_one_backdate.group_backdate_manager').id,
            ])]
        })
        
        # Create test partner
        self.partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'email': 'test@partner.com',
        })

    def test_backdate_log_creation(self):
        """Test that backdate operations are properly logged"""
        # Create a test invoice
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        # Post the invoice
        invoice.action_post()
        
        # Backdate the invoice
        new_date = fields.Date.today() - timedelta(days=5)
        old_date = invoice.invoice_date
        
        # Switch to backdate user
        invoice_as_user = invoice.with_user(self.backdate_manager)
        invoice_as_user.backdate_document(new_date, "Test reason")
        
        # Check that log was created
        log = self.env['backdate.log'].search([
            ('document_model', '=', 'account.move'),
            ('document_id', '=', invoice.id)
        ])
        
        self.assertEqual(len(log), 1)
        self.assertEqual(log.old_date.date(), old_date)
        self.assertEqual(log.new_date.date(), new_date)
        self.assertEqual(log.reason, "Test reason")

    def test_backdate_permission_check(self):
        """Test that only authorized users can backdate"""
        # Create a test invoice
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        # Post the invoice
        invoice.action_post()
        
        # Try to backdate without permission (should fail)
        new_date = fields.Date.today() - timedelta(days=5)
        
        with self.assertRaises(AccessError):
            invoice.backdate_document(new_date, "Test reason")

    def test_backdate_date_validation(self):
        """Test date validation rules"""
        # Create a test invoice
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        # Post the invoice
        invoice.action_post()
        
        # Switch to backdate user
        invoice_as_user = invoice.with_user(self.backdate_user)
        
        # Try to set future date (should fail)
        future_date = fields.Date.today() + timedelta(days=1)
        with self.assertRaises(UserError):
            invoice_as_user.backdate_document(future_date, "Test reason")
        
        # Try to backdate too far (should fail for regular user)
        # Set max days to 10
        self.env['ir.config_parameter'].sudo().set_param(
            'sh_all_in_one_backdate.backdate_max_days', '10'
        )
        
        old_date = fields.Date.today() - timedelta(days=15)
        with self.assertRaises(UserError):
            invoice_as_user.backdate_document(old_date, "Test reason")

    def test_wizard_functionality(self):
        """Test the backdate wizard"""
        # Create a test invoice
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        # Post the invoice
        invoice.action_post()
        
        # Create wizard
        wizard = self.env['backdate.wizard'].with_user(self.backdate_manager).create({
            'document_model': 'account.move',
            'document_id': invoice.id,
            'document_name': invoice.display_name,
            'current_date': invoice.invoice_date,
            'new_date': fields.Date.today() - timedelta(days=3),
            'reason': 'Test wizard backdate'
        })
        
        # Execute backdate
        wizard.action_backdate()
        
        # Check that invoice was backdated
        invoice.refresh()
        expected_date = fields.Date.today() - timedelta(days=3)
        self.assertEqual(invoice.invoice_date, expected_date)