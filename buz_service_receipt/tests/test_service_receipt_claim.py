# -*- coding: utf-8 -*-

from odoo import fields
from odoo.tests import tagged, TransactionCase


@tagged('-at_install', 'post_install')
class TestServiceTeam(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user1 = cls.env['res.users'].create({
            'name': 'Test Technician 1 - Team',
            'login': 'test_tech1_team@test.com',
            'groups_id': [(5, 0, 0)],
        })
        cls.user2 = cls.env['res.users'].create({
            'name': 'Test Technician 2 - Team',
            'login': 'test_tech2_team@test.com',
            'groups_id': [(5, 0, 0)],
        })
        cls.team = cls.env['service.team'].create({
            'name': 'Test Service Team',
            'member_ids': [(6, 0, [cls.user1.id, cls.user2.id])],
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Team Customer',
            'phone': '0812345678',
        })

    def test_01_team_onchange_fills_technicians(self):
        """Selecting a team auto-fills technician_ids via onchange."""
        receipt = self.env['service.receipt'].with_context(tracking_disable=True).new({
            'partner_id': self.partner.id,
            'request_date': fields.Date.today(),
        })
        self.assertFalse(receipt.technician_ids)
        receipt.update({'team_id': self.team.id})
        receipt._onchange_team_id()
        self.assertEqual(set(receipt.technician_ids.ids), {self.user1.id, self.user2.id})

    def test_02_team_name_unique(self):
        """Cannot create two teams with the same name."""
        import time
        team_name = 'Unique Team Name Test %s' % time.time()
        self.env['service.team'].create({'name': team_name})
        with self.assertRaises(Exception):
            self.env['service.team'].create({'name': team_name})

    def test_03_team_on_receipt(self):
        """Team is stored and can be searched."""
        receipt = self.env['service.receipt'].with_context(tracking_disable=True).create({
            'partner_id': self.partner.id,
            'team_id': self.team.id,
            'request_date': fields.Date.today(),
        })
        self.assertEqual(receipt.team_id, self.team)
        found = self.env['service.receipt'].search([('team_id', '=', self.team.id)])
        self.assertIn(receipt, found)


@tagged('-at_install', 'post_install')
class TestServiceReceiptClaim(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create partner for testing
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Claim Customer - TestServiceReceiptClaim',
            'phone': '0812345678',
        })

        # Create products (no tax)
        cls.product_original = cls.env['product.product'].create({
            'name': 'Test Original Product - Claim',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })
        cls.product_replacement = cls.env['product.product'].create({
            'name': 'Test Replacement Product - Claim',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })

    def _create_receipt(self, case_type='replacement'):
        """Helper to create a service receipt."""
        return self.env['service.receipt'].with_context(tracking_disable=True).create({
            'partner_id': self.partner.id,
            'requester_name': 'Test Requester',
            'service_case_type': case_type,
            'request_date': fields.Date.today(),
            'line_ids': [(0, 0, {
                'product_id': self.product_original.id,
                'quantity': 1.0,
                'resolution_type': 'replace',
                'replacement_product_id': self.product_replacement.id,
                'replacement_qty': 1.0,
            })],
        })

    def test_01_claim_workflow_full(self):
        """Full replacement claim workflow: draft → confirm → return picking → replacement delivery → done."""
        receipt = self._create_receipt('replacement')

        # Initially draft
        self.assertEqual(receipt.state, 'draft')
        self.assertEqual(receipt.service_case_type, 'replacement')

        # Confirm
        receipt.action_confirm()
        self.assertEqual(receipt.state, 'confirmed')

        # Start replacement flow → product_return
        receipt.action_waiting_replacement()
        self.assertEqual(receipt.state, 'product_return')
        self.assertTrue(receipt.claim_number)
        self.assertNotEqual(receipt.claim_number, 'New')

        # Create return picking
        receipt.action_create_return_picking()
        self.assertTrue(receipt.return_picking_id)
        self.assertEqual(receipt.return_picking_id.state, 'assigned')
        self.assertEqual(len(receipt.return_picking_id.move_ids), 1)
        self.assertEqual(receipt.return_picking_id.move_ids[0].product_id.id, self.product_original.id)

        # Validate return
        move = receipt.return_picking_id.move_ids
        move._set_quantity_done(move.product_uom_qty)
        receipt.return_picking_id.button_validate()
        self.assertEqual(receipt.return_picking_id.state, 'done')

        # Create replacement delivery (move from stock to customer)
        receipt.action_create_replacement_picking()
        self.assertTrue(receipt.replacement_picking_id)
        self.assertEqual(len(receipt.replacement_picking_id.move_ids), 1)
        self.assertEqual(receipt.replacement_picking_id.move_ids[0].product_id.id, self.product_replacement.id)
        self.assertEqual(receipt.state, 'replacement_delivery')

        # Validate replacement
        move2 = receipt.replacement_picking_id.move_ids
        move2._set_quantity_done(move2.product_uom_qty)
        receipt.replacement_picking_id.button_validate()
        self.assertEqual(receipt.replacement_picking_id.state, 'done')

        # Done
        receipt.action_done()
        self.assertEqual(receipt.state, 'done')

    def test_02_return_picking_no_lines(self):
        """Error when creating return picking without replace lines."""
        receipt = self._create_receipt('replacement')
        receipt.action_confirm()
        receipt.action_waiting_replacement()

        # Remove product from lines
        receipt.line_ids.write({'product_id': False})

        with self.assertRaises(Exception):
            receipt.action_create_return_picking()

    def test_03_replacement_picking_no_lines(self):
        """Error when creating replacement picking without replacement product."""
        receipt = self._create_receipt('replacement')
        receipt.action_confirm()
        receipt.action_waiting_replacement()
        receipt.action_create_return_picking()

        # Remove replacement product
        receipt.line_ids.write({'replacement_product_id': False})

        with self.assertRaises(Exception):
            receipt.action_create_replacement_picking()

    def test_04_create_sale_order(self):
        """Create sale order for chargeable service."""
        receipt = self._create_receipt('service')
        receipt.write({
            'charge_customer': True,
        })
        receipt.line_ids.write({
            'bill_customer': True,
            'price_unit': 500.0,
        })
        receipt.action_confirm()

        # Create sale order
        receipt.action_create_sale_order()
        self.assertTrue(receipt.sale_order_id)
        self.assertEqual(len(receipt.sale_order_id.order_line), 1)
        self.assertEqual(receipt.sale_order_id.order_line[0].price_unit, 500.0)
        self.assertEqual(receipt.sale_order_id.partner_id.id, self.partner.id)

        # View sale order
        action = receipt.action_view_sale_order()
        self.assertEqual(action['res_id'], receipt.sale_order_id.id)

    def test_05_view_actions(self):
        """View actions for pickings and sale order."""
        receipt = self._create_receipt('replacement')
        receipt.action_confirm()
        receipt.action_waiting_replacement()
        receipt.action_create_return_picking()

        # View return
        action = receipt.action_view_return_picking()
        self.assertEqual(action['res_id'], receipt.return_picking_id.id)

        # View pickings
        action_pick = receipt.action_view_pickings()
        self.assertEqual(action_pick['res_model'], 'stock.picking')

    def test_06_picking_counts(self):
        """Compute fields for picking counts."""
        receipt = self._create_receipt('replacement')
        receipt.action_confirm()
        receipt.action_waiting_replacement()

        # No pickings yet
        self.assertEqual(receipt.return_picking_count, 0)
        self.assertEqual(receipt.replacement_picking_count, 0)
        self.assertEqual(receipt.picking_count, 0)

        # Create return
        receipt.action_create_return_picking()
        self.assertEqual(receipt.return_picking_count, 1)
        self.assertEqual(receipt.picking_count, 1)

        # Create replacement
        receipt.action_create_replacement_picking()
        self.assertEqual(receipt.replacement_picking_count, 1)
        self.assertEqual(receipt.picking_count, 2)

    def test_07_cancel_draft(self):
        """Cancel and reset to draft."""
        receipt = self._create_receipt('replacement')
        receipt.action_confirm()
        self.assertEqual(receipt.state, 'confirmed')

        receipt.action_cancel()
        self.assertEqual(receipt.state, 'cancel')

        receipt.action_draft()
        self.assertEqual(receipt.state, 'draft')

    def test_08_create_uses_receipt_sequence(self):
        """Service.receipt sequence always used for name, never claim_number."""
        receipt = self._create_receipt('replacement')
        # name should start with SRV/ (service.receipt sequence prefix)
        self.assertTrue(
            receipt.name.startswith('SRV/'),
            f"Name should use service.receipt sequence, got: {receipt.name}"
        )
        # claim_number should still be 'New' (default) — not auto-generated
        self.assertEqual(receipt.claim_number, 'New',
                         "claim_number should not be auto-generated on create")

    def test_09_default_get_generates_claim_number(self):
        """default_get pre-generates claim_number when context has default_service_case_type='replacement'."""
        vals = self.env['service.receipt'].with_context(
            default_service_case_type='replacement'
        ).default_get(['claim_number', 'service_case_type'])
        self.assertTrue(vals.get('claim_number'), "claim_number should be pre-generated")
        self.assertNotEqual(vals.get('claim_number'), 'New')
        self.assertTrue(
            vals['claim_number'].startswith('MCP'),
            f"Claim number should start with MCP, got: {vals.get('claim_number')}"
        )

    def test_10_action_create_claim_generates_number(self):
        """action_create_claim generates claim_number and returns claim form action."""
        receipt = self._create_receipt('service')
        self.assertEqual(receipt.claim_number, 'New',
                         "Claim number should still be default 'New'")

        result = receipt.action_create_claim()
        # claim_number should now be generated
        self.assertNotEqual(receipt.claim_number, 'New')
        self.assertTrue(
            receipt.claim_number.startswith('MCP'),
            f"Claim number should start with MCP, got: {receipt.claim_number}"
        )
        # service_case_type should be 'replacement'
        self.assertEqual(receipt.service_case_type, 'replacement')
        # action should open claim form
        self.assertEqual(result['res_model'], 'service.receipt')
        self.assertEqual(result['res_id'], receipt.id)
        self.assertEqual(result['view_mode'], 'form')
        self.assertEqual(result['target'], 'current')

    def test_11_no_auto_claim_on_create_replacement(self):
        """Creating a receipt with replacement type does NOT auto-generate claim_number."""
        receipt = self._create_receipt('replacement')
        # claim_number should NOT be set by create (only by action_create_claim)
        self.assertEqual(receipt.claim_number, 'New',
                         "claim_number should not be auto-set by create()")


@tagged('-at_install', 'post_install')
class TestServiceReceiptPickingTypeConfig(TransactionCase):
    """Test that company-level picking type config overrides warehouse defaults."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Picking Type Customer',
            'phone': '0899999999',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product - PickingType',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })
        cls.product_replacement = cls.env['product.product'].create({
            'name': 'Test Replacement - PickingType',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })

        # Get warehouse for company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1,
        )

        # Create custom picking types for testing
        cls.custom_return_type = cls.env['stock.picking.type'].create({
            'name': 'Claim Return',
            'code': 'incoming',
            'warehouse_id': cls.warehouse.id,
            'sequence_code': 'CLM/RT',
            'company_id': cls.env.company.id,
        })
        cls.custom_replacement_type = cls.env['stock.picking.type'].create({
            'name': 'Claim Replacement',
            'code': 'outgoing',
            'warehouse_id': cls.warehouse.id,
            'sequence_code': 'CLM/RP',
            'company_id': cls.env.company.id,
        })

    def _create_receipt(self):
        return self.env['service.receipt'].with_context(tracking_disable=True).create({
            'partner_id': self.partner.id,
            'service_case_type': 'replacement',
            'request_date': fields.Date.today(),
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'resolution_type': 'replace',
                'replacement_product_id': self.product_replacement.id,
                'replacement_qty': 1.0,
            })],
        })

    def test_01_default_picking_type(self):
        """Without config, falls back to warehouse picking types."""
        receipt = self._create_receipt()
        receipt.action_confirm()
        receipt.action_waiting_replacement()

        return_type = receipt._get_claim_picking_type('incoming')
        self.assertEqual(return_type.code, 'incoming')

        replacement_type = receipt._get_claim_picking_type('outgoing')
        self.assertEqual(replacement_type.code, 'outgoing')

    def test_02_custom_return_picking_type(self):
        """Configured return picking type is used for return pickings."""
        # Set config
        self.env.company.service_receipt_return_picking_type_id = self.custom_return_type

        receipt = self._create_receipt()
        receipt.action_confirm()
        receipt.action_waiting_replacement()
        receipt.action_create_return_picking()

        self.assertEqual(
            receipt.return_picking_id.picking_type_id,
            self.custom_return_type,
        )
        # Document name should use the custom sequence code
        self.assertTrue(receipt.return_picking_id.name)

    def test_03_custom_replacement_picking_type(self):
        """Configured replacement picking type is used for replacement deliveries."""
        # Set config
        self.env.company.service_receipt_replacement_picking_type_id = self.custom_replacement_type

        receipt = self._create_receipt()
        receipt.action_confirm()
        receipt.action_waiting_replacement()
        receipt.action_create_return_picking()

        # Validate return first
        move = receipt.return_picking_id.move_ids
        move._set_quantity_done(move.product_uom_qty)
        receipt.return_picking_id.button_validate()

        receipt.action_create_replacement_picking()

        self.assertEqual(
            receipt.replacement_picking_id.picking_type_id,
            self.custom_replacement_type,
        )

    def test_04_config_via_settings(self):
        """Picking type can be set via res.config.settings."""
        settings = self.env['res.config.settings'].create({
            'service_receipt_return_picking_type_id': self.custom_return_type.id,
            'service_receipt_replacement_picking_type_id': self.custom_replacement_type.id,
        })
        settings.execute()

        self.assertEqual(
            self.env.company.service_receipt_return_picking_type_id,
            self.custom_return_type,
        )
        self.assertEqual(
            self.env.company.service_receipt_replacement_picking_type_id,
            self.custom_replacement_type,
        )
