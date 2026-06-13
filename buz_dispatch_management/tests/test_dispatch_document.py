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
            'name': 'Test Product - Dispatch',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer - Dispatch',
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

    def _create_doc(self, picking=None, state='draft'):
        picking = picking or self.picking
        doc = self.env['buz.dispatch.document'].create({
            'picking_id': picking.id,
            'partner_id': picking.partner_id.id,
            'dispatch_date': fields.Date.today(),
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_id': self.product.uom_id.id,
                'ordered_qty': 10.0,
                'dispatch_qty': 10.0,
            })],
        })
        if state == 'draft':
            pass
        elif state == 'printed':
            doc.write({'state': 'printed'})
        elif state == 'in_transit':
            doc.write({'state': 'in_transit'})
        elif state == 'delivered':
            doc.write({'state': 'delivered'})
        elif state == 'posted':
            picking.action_assign()
            picking.button_validate()
            doc.write({'state': 'posted', 'posted_date': fields.Datetime.now()})
        elif state == 'cancel':
            doc.write({'state': 'cancel'})
        return doc

    def test_01_create_draft(self):
        doc = self._create_doc()
        self.assertEqual(doc.state, 'draft')
        self.assertTrue(doc.name)
        self.assertTrue(doc.name.startswith('DSP/'))

    def test_02_print_updates_tracking(self):
        doc = self._create_doc(state='draft')
        self.assertEqual(doc.print_count, 0)
        self.assertFalse(doc.printed_by)

        doc.action_print()

        self.assertEqual(doc.print_count, 1)
        self.assertTrue(doc.first_print_date)
        self.assertTrue(doc.last_print_date)
        self.assertEqual(doc.printed_by, self.env.user)
        self.assertEqual(doc.state, 'printed')

    def test_03_print_count_increment(self):
        doc = self._create_doc(state='printed')
        old_count = doc.print_count
        doc.action_print()
        self.assertEqual(doc.print_count, old_count + 1)

    def test_04_post_validates_picking(self):
        doc = self._create_doc(state='delivered')
        self.assertNotEqual(self.picking.state, 'done')
        doc.action_post()
        self.assertEqual(doc.state, 'posted')
        self.assertTrue(doc.posted_date)
        self.assertEqual(self.picking.state, 'done')

    def test_05_cannot_post_canceled(self):
        doc = self._create_doc(state='cancel')
        with self.assertRaises(UserError):
            doc.action_post()

    def test_06_cannot_post_already_posted(self):
        doc = self._create_doc(state='posted')
        with self.assertRaises(UserError):
            doc.action_post()

    def test_07_cannot_delete_posted(self):
        doc = self._create_doc(state='posted')
        with self.assertRaises(UserError):
            doc.unlink()

    def test_08_cancel_flow(self):
        doc = self._create_doc(state='draft')
        doc.action_cancel()
        self.assertEqual(doc.state, 'cancel')

    def test_09_cannot_cancel_posted(self):
        doc = self._create_doc(state='posted')
        with self.assertRaises(UserError):
            doc.action_cancel()

    def test_10_in_transit_flow(self):
        doc = self._create_doc(state='printed')
        doc.action_in_transit()
        self.assertEqual(doc.state, 'in_transit')

    def test_11_deliver_flow(self):
        doc = self._create_doc(state='in_transit')
        doc.action_deliver()
        self.assertEqual(doc.state, 'delivered')

    def test_12_set_draft_from_cancel(self):
        doc = self._create_doc(state='cancel')
        doc.action_set_draft()
        self.assertEqual(doc.state, 'draft')

    def test_13_cron_auto_posts_delivered(self):
        yesterday = fields.Date.today() - timedelta(days=1)
        doc = self._create_doc(state='delivered')
        doc.dispatch_date = yesterday

        self.env['buz.dispatch.document'].cron_auto_post()

        self.assertEqual(doc.state, 'posted')
        self.assertEqual(self.picking.state, 'done')

    def test_14_cron_skips_future(self):
        tomorrow = fields.Date.today() + timedelta(days=3)
        doc = self._create_doc(state='delivered')
        doc.dispatch_date = tomorrow

        self.env['buz.dispatch.document'].cron_auto_post()

        self.assertEqual(doc.state, 'delivered')

    def test_15_remaining_qty_computation(self):
        doc1 = self._create_doc()
        self.assertEqual(doc1.remaining_qty, 0.0)

        doc1.line_ids.write({'dispatch_qty': 6.0})

        self.assertEqual(doc1.remaining_qty, 4.0)
