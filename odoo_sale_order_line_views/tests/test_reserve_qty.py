from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReserveQty(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # buz_validate_control, where installed, limits who may validate.
        validators = cls.env.ref(
            'buz_validate_control.group_validate_privileged',
            raise_if_not_found=False)
        if validators:
            cls.env.user.groups_id = [Command.link(validators.id)]
        # Own one-step warehouse, so existing delivery routes cannot leave the
        # customer moves waiting on a pick or pack step.
        cls.warehouse = cls.env['stock.warehouse'].create({
            'name': 'Reserve Qty Test',
            'code': 'RQT',
            'company_id': cls.env.company.id,
            'delivery_steps': 'ship_only',
        })
        cls.stock = cls.warehouse.lot_stock_id
        # The context key skips the address checks of
        # buz_partner_required_fields where that module is installed.
        cls.partner = cls.env['res.partner'].with_context(
            skip_partner_required_fields=True).create({'name': 'Customer'})
        cls.comp_a = cls._product('Component A')
        cls.comp_b = cls._product('Component B')
        cls.kit = cls._product('Kit')
        cls.bom = cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.kit.product_tmpl_id.id,
            'product_qty': 1.0,
            'type': 'phantom',
            'bom_line_ids': [
                Command.create({'product_id': cls.comp_a.id, 'product_qty': 1.0}),
                Command.create({'product_id': cls.comp_b.id, 'product_qty': 4.0}),
            ],
        })

    @classmethod
    def _product(cls, name):
        return cls.env['product.product'].create(
            {'name': name, 'detailed_type': 'product'})

    def _stock(self, product, qty):
        self.env['stock.quant']._update_available_quantity(product, self.stock, qty)

    def _order(self, product, qty):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'order_line': [Command.create(
                {'product_id': product.id, 'product_uom_qty': qty})],
        })
        order.action_confirm()
        self._assign(order.picking_ids)
        return order

    def _assign(self, pickings):
        # buz_stock_reservation_guard, where installed, refuses to reserve a
        # transfer with an out-of-stock product. Some cases need exactly that.
        if 'bypass_reservation_guard' in pickings._fields:
            pickings.bypass_reservation_guard = True
        pickings.action_assign()

    def _reserve(self, order):
        order.order_line.invalidate_recordset(['reserve_qty'])
        return order.order_line.reserve_qty

    def test_non_kit_shows_reserved_quantity(self):
        self._stock(self.comp_a, 3)
        order = self._order(self.comp_a, 5)
        self.assertEqual(self._reserve(order), 3)

    def test_kit_counts_sets_not_component_pieces(self):
        self._stock(self.comp_a, 5)
        self._stock(self.comp_b, 20)
        order = self._order(self.kit, 5)
        self.assertEqual(self._reserve(order), 5)

    def test_kit_is_limited_by_shortest_component(self):
        self._stock(self.comp_a, 5)
        self._stock(self.comp_b, 14)  # 3.5 sets
        order = self._order(self.kit, 5)
        self.assertEqual(self._reserve(order), 3)

    def test_kit_with_unreserved_component_is_zero(self):
        self._stock(self.comp_a, 5)
        order = self._order(self.kit, 5)
        self.assertEqual(self._reserve(order), 0)

    def test_kit_after_uneven_partial_delivery(self):
        self._stock(self.comp_a, 8)
        self._stock(self.comp_b, 20)
        order = self._order(self.kit, 10)  # A reserves 8/10, B 20/40
        picking = order.picking_ids
        # Test stock has no valuation layers, so skip the per-warehouse
        # balance check of stock_fifo_by_location where that is installed.
        picking.with_context(
            skip_backorder=True,
            skip_warehouse_consistency_check=True).button_validate()
        self.assertEqual(order.order_line.qty_delivered, 5)
        backorder = order.picking_ids - picking
        self._stock(self.comp_b, 20)
        self._assign(backorder)
        # 8 A already shipped, 2 still unreserved: 3 of the 5 pending sets
        # are complete.
        self.assertEqual(self._reserve(order), 3)
        self._stock(self.comp_a, 2)
        self._assign(backorder)
        self.assertEqual(self._reserve(order), 5)

    def test_kit_when_moves_cover_less_than_ordered_quantity(self):
        self._stock(self.comp_a, 6)
        self._stock(self.comp_b, 24)
        order = self._order(self.kit, 18)
        # Same shape as lines whose remaining demand was cut on the transfer.
        for move in order.order_line.move_ids:
            move.product_uom_qty = move.quantity
        self.assertEqual(order.order_line.qty_delivered, 0)
        self.assertEqual(self._reserve(order), 6)

    def test_nested_kit(self):
        outer = self._product('Outer Kit')
        self.env['mrp.bom'].create({
            'product_tmpl_id': outer.product_tmpl_id.id,
            'product_qty': 1.0,
            'type': 'phantom',
            'bom_line_ids': [
                Command.create({'product_id': self.kit.id, 'product_qty': 2.0}),
            ],
        })
        self._stock(self.comp_a, 6)
        self._stock(self.comp_b, 40)
        order = self._order(outer, 5)  # needs A 10, B 40
        self.assertEqual(self._reserve(order), 3)

    def test_kit_ignores_bom_changes_made_after_confirmation(self):
        self._stock(self.comp_a, 5)
        self._stock(self.comp_b, 20)
        order = self._order(self.kit, 5)
        extra = self._product('Component C')
        self.bom.write({'bom_line_ids': [
            Command.create({'product_id': extra.id, 'product_qty': 1.0})]})
        self.assertEqual(self._reserve(order), 5)
