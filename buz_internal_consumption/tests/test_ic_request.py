from odoo.tests import TransactionCase, tagged
from odoo import fields
from odoo.exceptions import ValidationError, UserError


@tagged('post_install', '-at_install')
class TestICRequest(TransactionCase):

    def setUp(self):
        super().setUp()
        
        # Common test data
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'testuser',
            'email': 'testuser@example.com',
        })
        
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'product',
            'standard_price': 10.0,
            'list_price': 15.0,
        })
        
        self.location = self.env['stock.location'].create({
            'name': 'Test Location',
            'usage': 'internal',
        })
        
        self.dest_location = self.env['stock.location'].create({
            'name': 'Consumption Location',
            'usage': 'consume',
        })
        
        self.analytic_account = self.env['account.analytic.account'].create({
            'name': 'Test Analytic Account',
        })
        
        self.journal = self.env['account.journal'].create({
            'name': 'Test Journal',
            'code': 'TST',
            'type': 'general',
        })

    def test_create_ic_request(self):
        """Test creating an IC request"""
        request = self.env['ic.request'].create({
            'requester_id': self.user.id,
            'location_id': self.location.id,
            'dest_location_id': self.dest_location.id,
            'date_request': fields.Date.today(),
        })
        
        self.assertTrue(request.name.startswith('IC/'))
        self.assertEqual(request.state, 'draft')
        self.assertEqual(request.requester_id, self.user)

    def test_add_request_line(self):
        """Test adding a line to the request"""
        request = self.env['ic.request'].create({
            'requester_id': self.user.id,
            'location_id': self.location.id,
            'dest_location_id': self.dest_location.id,
        })
        
        line = self.env['ic.request.line'].create({
            'request_id': request.id,
            'product_id': self.product.id,
            'qty': 5.0,
            'uom_id': self.product.uom_id.id,
        })
        
        request.line_ids = [(4, line.id)]
        self.assertEqual(len(request.line_ids), 1)
        self.assertEqual(request.line_ids[0].product_id, self.product)
        self.assertEqual(request.line_ids[0].qty, 5.0)

    def test_submit_request(self):
        """Test submitting a request"""
        request = self.env['ic.request'].create({
            'requester_id': self.user.id,
            'location_id': self.location.id,
            'dest_location_id': self.dest_location.id,
        })
        
        line = self.env['ic.request.line'].create({
            'request_id': request.id,
            'product_id': self.product.id,
            'qty': 5.0,
            'uom_id': self.product.uom_id.id,
        })
        
        request.line_ids = [(4, line.id)]
        
        # Submit the request
        request.action_submit()
        self.assertEqual(request.state, 'submitted')

    def test_submit_request_without_lines(self):
        """Test that submitting a request without lines raises an error"""
        request = self.env['ic.request'].create({
            'requester_id': self.user.id,
            'location_id': self.location.id,
            'dest_location_id': self.dest_location.id,
        })
        
        with self.assertRaises(ValidationError):
            request.action_submit()

    def test_approve_request(self):
        """Test approving a request"""
        request = self.env['ic.request'].create({
            'requester_id': self.user.id,
            'location_id': self.location.id,
            'dest_location_id': self.dest_location.id,
            'state': 'submitted',
        })
        
        line = self.env['ic.request.line'].create({
            'request_id': request.id,
            'product_id': self.product.id,
            'qty': 5.0,
            'uom_id': self.product.uom_id.id,
        })
        
        request.line_ids = [(4, line.id)]
        
        # Approve the request
        request.action_approve()
        self.assertEqual(request.state, 'manager_approved')

    def test_compute_amount_total_cost(self):
        """Test that total cost is computed correctly"""
        request = self.env['ic.request'].create({
            'requester_id': self.user.id,
            'location_id': self.location.id,
            'dest_location_id': self.dest_location.id,
        })
        
        line1 = self.env['ic.request.line'].create({
            'request_id': request.id,
            'product_id': self.product.id,
            'qty': 5.0,
            'uom_id': self.product.uom_id.id,
        })
        
        line2 = self.env['ic.request.line'].create({
            'request_id': request.id,
            'product_id': self.product.id,
            'qty': 3.0,
            'uom_id': self.product.uom_id.id,
        })
        
        request.line_ids = [(4, line1.id), (4, line2.id)]
        
        expected_total = (5.0 * self.product.standard_price) + (3.0 * self.product.standard_price)
        self.assertEqual(request.amount_total_cost, expected_total)

    def test_unit_cost_computation(self):
        """Test that unit cost is computed based on policy"""
        request = self.env['ic.request'].create({
            'requester_id': self.user.id,
            'location_id': self.location.id,
            'dest_location_id': self.dest_location.id,
            'expense_policy': 'standard_cost',
        })
        
        line = self.env['ic.request.line'].create({
            'request_id': request.id,
            'product_id': self.product.id,
            'qty': 5.0,
            'uom_id': self.product.uom_id.id,
        })
        
        # With standard cost policy, unit cost should equal product's standard price
        self.assertEqual(line.unit_cost, self.product.standard_price)