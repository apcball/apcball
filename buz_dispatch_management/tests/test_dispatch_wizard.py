from odoo.tests import common, tagged
from odoo.exceptions import UserError


@tagged('at_install', 'post_install')
class TestDispatchWizard(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.product_a = cls.env['product.product'].create({
            'name': 'Product A',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })
        cls.product_b = cls.env['product.product'].create({
            'name': 'Product B',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Wizard Test Customer',
        })

        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref('stock.stock_location_customers')

        for p in [cls.product_a, cls.product_b]:
            cls.env['stock.quant'].create({
                'product_id': p.id,
                'location_id': cls.stock_location.id,
                'quantity': 100.0,
            })

        cls.picking = cls.env['stock.picking'].create({
            'picking_type_id': cls.warehouse.out_type_id.id,
            'partner_id': cls.partner.id,
            'location_id': cls.stock_location.id,
            'location_dest_id': cls.customer_location.id,
        })

        cls.move_a = cls.env['stock.move'].create({
            'name': cls.product_a.display_name,
            'product_id': cls.product_a.id,
            'product_uom_qty': 10.0,
            'product_uom': cls.product_a.uom_id.id,
            'picking_id': cls.picking.id,
            'location_id': cls.stock_location.id,
            'location_dest_id': cls.customer_location.id,
            'quantity': 10.0,
            'state': 'draft',
        })
        cls.move_b = cls.env['stock.move'].create({
            'name': cls.product_b.display_name,
            'product_id': cls.product_b.id,
            'product_uom_qty': 20.0,
            'product_uom': cls.product_b.uom_id.id,
            'picking_id': cls.picking.id,
            'location_id': cls.stock_location.id,
            'location_dest_id': cls.customer_location.id,
            'quantity': 20.0,
            'state': 'draft',
        })

        cls.picking.action_confirm()
        cls.move_a.quantity = 10.0
        cls.move_a.picked = True
        cls.move_b.quantity = 20.0
        cls.move_b.picked = True
        cls.picking.action_assign()

    def test_01_wizard_defaults(self):
        wizard = self.env['buz.create.dispatch.wizard'].with_context(
            default_picking_id=self.picking.id
        ).create({})
        self.assertEqual(wizard.picking_id, self.picking)
        self.assertEqual(wizard.partner_id, self.partner)
        self.assertEqual(len(wizard.line_ids), 2)

    def test_02_wizard_full_dispatch(self):
        wizard = self.env['buz.create.dispatch.wizard'].with_context(
            default_picking_id=self.picking.id
        ).create({})
        for line in wizard.line_ids:
            line.dispatch_qty = line.ordered_qty

        result = wizard.action_create_dispatch()
        self.assertEqual(result['res_model'], 'buz.dispatch.document')

        doc = self.env['buz.dispatch.document'].browse(result['res_id'])
        self.assertEqual(len(doc.line_ids), 2)
        self.assertEqual(doc.state, 'draft')
        self.assertEqual(doc.picking_id, self.picking)

    def test_03_wizard_partial_dispatch(self):
        wizard = self.env['buz.create.dispatch.wizard'].with_context(
            default_picking_id=self.picking.id
        ).create({})
        for line in wizard.line_ids:
            line.dispatch_qty = line.ordered_qty / 2

        result = wizard.action_create_dispatch()
        doc = self.env['buz.dispatch.document'].browse(result['res_id'])
        self.assertEqual(sum(doc.line_ids.mapped('dispatch_qty')), 15.0)

    def test_04_wizard_second_partial_dispatch(self):
        wiz1 = self.env['buz.create.dispatch.wizard'].with_context(
            default_picking_id=self.picking.id
        ).create({})
        for line in wiz1.line_ids:
            if line.product_id == self.product_a:
                line.dispatch_qty = 6.0
            else:
                line.dispatch_qty = 10.0
        wiz1.action_create_dispatch()

        wiz2 = self.env['buz.create.dispatch.wizard'].with_context(
            default_picking_id=self.picking.id
        ).create({})
        for line in wiz2.line_ids:
            if line.product_id == self.product_a:
                self.assertEqual(line.ordered_qty, 10.0)
                self.assertEqual(line.dispatch_qty, 4.0)
            else:
                self.assertEqual(line.ordered_qty, 20.0)
                self.assertEqual(line.dispatch_qty, 10.0)

    def test_05_wizard_prevents_over_dispatch(self):
        wiz1 = self.env['buz.create.dispatch.wizard'].with_context(
            default_picking_id=self.picking.id
        ).create({})
        for line in wiz1.line_ids:
            if line.product_id == self.product_a:
                line.dispatch_qty = 7.0
            else:
                line.dispatch_qty = 15.0
        wiz1.action_create_dispatch()

        wiz2 = self.env['buz.create.dispatch.wizard'].with_context(
            default_picking_id=self.picking.id
        ).create({})
        for line in wiz2.line_ids:
            if line.product_id == self.product_a:
                line.dispatch_qty = 5.0
        with self.assertRaises(UserError):
            wiz2.action_create_dispatch()

    def test_06_wizard_zero_qty_raises_error(self):
        wizard = self.env['buz.create.dispatch.wizard'].with_context(
            default_picking_id=self.picking.id
        ).create({})
        for line in wizard.line_ids:
            line.dispatch_qty = 0
        with self.assertRaises(UserError):
            wizard.action_create_dispatch()

    def test_07_wizard_no_lines_raises_error(self):
        picking2 = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id,
            'partner_id': self.partner.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.customer_location.id,
        })
        wizard = self.env['buz.create.dispatch.wizard'].with_context(
            default_picking_id=picking2.id
        ).create({})
        with self.assertRaises(UserError):
            wizard.action_create_dispatch()
