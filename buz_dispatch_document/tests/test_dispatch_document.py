from datetime import timedelta

from odoo import fields
from odoo.tests import common, tagged
from odoo.exceptions import UserError


@tagged('at_install', 'post_install')
class TestDispatchDocument(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.product = cls.env['product.product'].create({
            'name': 'Test Product - Dispatch Document',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer - Dispatch Document',
            'street': '123 Test St',
            'city': 'Bangkok',
            'zip': '10110',
            'phone': '02-123-4567',
        })

        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        cls.picking_type_out = cls.warehouse.out_type_id
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref('stock.stock_location_customers')

        cls.env['stock.quant'].create({
            'product_id': cls.product.id,
            'location_id': cls.stock_location.id,
            'quantity': 100.0,
        })

        cls.picking = cls.env['stock.picking'].create({
            'picking_type_id': cls.picking_type_out.id,
            'partner_id': cls.partner.id,
            'location_id': cls.stock_location.id,
            'location_dest_id': cls.customer_location.id,
        })

        cls.move = cls.env['stock.move'].create({
            'name': cls.product.display_name,
            'product_id': cls.product.id,
            'product_uom_qty': 10.0,
            'product_uom': cls.product.uom_id.id,
            'picking_id': cls.picking.id,
            'location_id': cls.stock_location.id,
            'location_dest_id': cls.customer_location.id,
            'quantity': 10.0,
            'state': 'draft',
        })

        cls.picking.action_confirm()
        cls.move.quantity = 10.0
        cls.move.picked = True
        cls.picking.action_assign()

    def _create_picking(self):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.picking_type_out.id,
            'partner_id': self.partner.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.customer_location.id,
        })
        move = self.env['stock.move'].create({
            'name': self.product.display_name,
            'product_id': self.product.id,
            'product_uom_qty': 5.0,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.customer_location.id,
            'quantity': 5.0,
            'state': 'draft',
        })
        picking.action_confirm()
        move.quantity = 5.0
        move.picked = True
        picking.action_assign()
        return picking

    # === Basic CRUD ===

    def test_01_create_draft(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        self.assertEqual(doc.state, 'draft')
        self.assertFalse(doc.name)
        expected_date = fields.Date.today() + timedelta(days=1)
        self.assertEqual(doc.document_date, expected_date)

    def test_02_confirm_runs_sequence(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        self.assertEqual(doc.state, 'confirmed')
        self.assertTrue(doc.name)
        self.assertTrue(doc.name.startswith('DD/'))

    def test_03_confirm_twice_raises_error(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        with self.assertRaises(UserError):
            doc.action_confirm()

    def test_04_set_draft_from_confirmed(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        self.assertEqual(doc.state, 'confirmed')
        doc.action_set_draft()
        self.assertEqual(doc.state, 'draft')

    # === Schedule (validate) behavior ===

    def test_05_schedule_sets_done_but_does_not_validate_picking(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        self.assertEqual(doc.stock_picking_id.state, 'assigned')

        doc.action_validate()
        self.assertEqual(doc.state, 'done')
        self.assertEqual(doc.stock_picking_id.state, 'assigned',
                         'Stock picking should NOT be validated by schedule action')

    def test_06_schedule_draft_raises_error(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        with self.assertRaises(UserError):
            doc.action_validate()

    def test_07_set_draft_from_done_raises_error(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        doc.action_validate()
        with self.assertRaises(UserError):
            doc.action_set_draft()

    # === Cron auto-validation ===

    def test_08_cron_validates_picking_for_done_docs(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
            'document_date': fields.Date.today() - timedelta(days=1),
        })
        doc.action_confirm()
        doc.action_validate()
        self.assertEqual(doc.state, 'done')
        self.assertEqual(doc.stock_picking_id.state, 'assigned',
                         'Picking should still be assigned before cron')

        self.env['buz.dispatch.document'].action_validate_cron()
        self.assertEqual(doc.stock_picking_id.state, 'done',
                         'Cron should validate the picking')

    def test_09_cron_skips_future_document_date(self):
        picking2 = self._create_picking()
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': picking2.id,
            'document_date': fields.Date.today() + timedelta(days=3),
        })
        doc.action_confirm()
        doc.action_validate()
        self.assertEqual(doc.state, 'done')

        self.env['buz.dispatch.document'].action_validate_cron()
        self.assertIn(doc.stock_picking_id.state, ('confirmed', 'assigned'),
                      'Picking should NOT be validated for future document_date')

    def test_10_cron_skips_already_validated_picking(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
            'document_date': fields.Date.today(),
        })
        doc.action_confirm()
        doc.action_validate()
        self.picking.button_validate()
        self.assertEqual(self.picking.state, 'done')

        self.env['buz.dispatch.document'].action_validate_cron()
        self.assertEqual(doc.state, 'done',
                         'Cron should not fail on already-validated picking')

    def test_11_cron_only_processes_done_docs(self):
        picking2 = self._create_picking()
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': picking2.id,
            'document_date': fields.Date.today(),
        })
        doc.action_confirm()
        self.assertEqual(doc.state, 'confirmed')

        self.env['buz.dispatch.document'].action_validate_cron()
        self.assertEqual(doc.stock_picking_id.state, 'assigned',
                         'Cron should skip confirmed-only docs')

    # === Related fields ===

    def test_12_related_fields_match_picking(self):
        self.picking.write({
            'vehicle_type': 'Truck',
            'vehicle_plate': 'กข1234',
            'driver': 'John Doe',
            'sub_district': 'Phra Khanong',
            'delivery_note': 'Handle with care',
        })
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        self.assertEqual(doc.partner_id, self.partner)
        self.assertEqual(doc.partner_street, '123 Test St')
        self.assertEqual(doc.partner_city, 'Bangkok')
        self.assertEqual(doc.partner_zip, '10110')
        self.assertEqual(doc.partner_phone, '02-123-4567')
        self.assertEqual(doc.vehicle_type, 'Truck')
        self.assertEqual(doc.vehicle_plate, 'กข1234')
        self.assertEqual(doc.driver, 'John Doe')
        self.assertEqual(doc.sub_district, 'Phra Khanong')
        self.assertEqual(doc.delivery_note, 'Handle with care')

    def test_13_move_lines_computed(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        self.assertEqual(len(doc.move_ids_without_package), 1)
        move = doc.move_ids_without_package[0]
        self.assertEqual(move.product_id, self.product)
        self.assertEqual(move.product_uom_qty, 10.0)

    # === Print action ===

    def test_14_print_action_returns_report(self):
        doc = self.env['buz.dispatch.document'].create({
            'stock_picking_id': self.picking.id,
        })
        doc.action_confirm()
        result = doc.action_print_dispatch()
        self.assertEqual(result['type'], 'ir.actions.report')
        self.assertEqual(result['report_name'],
                         'buz_inventory_delivery_report.dispatch_report_document')
