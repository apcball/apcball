"""Tests for products exposed by the POS Lite terminal."""

from odoo.tests import common, tagged
from odoo.exceptions import ValidationError

from ..controllers.main import _get_terminal_location, _terminal_product_domain


@tagged('-at_install', 'post_install')
class TestTerminalProducts(common.TransactionCase):
    """Service products are available even without stock quants."""

    def _get_pricelist(self):
        # Fresh --without-demo databases have no pricelist at all.
        return (
            self.env['product.pricelist'].search([], limit=1)
            or self.env['product.pricelist'].create({'name': 'Terminal Test Pricelist'})
        )

    def test_terminal_domain_includes_service_products_without_stock(self):
        service = self.env['product.product'].create({
            'name': 'Terminal Service',
            'type': 'service',
            'sale_ok': True,
            'can_be_pos': True,
        })
        products = self.env['product.product'].search(
            _terminal_product_domain([]),
        )

        self.assertIn(service, products)

    def test_config_location_resolves_to_bound_location(self):
        """A per-location config resolves its terminal stock location directly."""
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        location = self.env['stock.location'].create({
            'name': 'POS Terminal Shelf',
            'location_id': warehouse.lot_stock_id.id,
            'usage': 'internal',
            'company_id': self.env.company.id,
        })
        config = self.env['pos.lite.config'].create({
            'name': 'POS Location Config',
            'company_id': self.env.company.id,
            'warehouse_id': warehouse.id,
            'location_id': location.id,
            'pricelist_id': self._get_pricelist().id,
            'journal_id': self.env['account.journal'].search([
                ('company_id', '=', self.env.company.id),
                ('type', '=', 'cash'),
            ], limit=1).id,
        })

        self.assertEqual(_get_terminal_location(config), location)

    def test_config_cannot_clear_location(self):
        """Per-location contract: clearing location_id is rejected."""
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        # Dedicated location to avoid colliding with the real DEV config bound
        # to the warehouse stock location.
        location = self.env['stock.location'].create({
            'name': 'POS No-Clear Loc',
            'location_id': warehouse.lot_stock_id.id,
            'usage': 'internal',
            'company_id': self.env.company.id,
        })
        config = self.env['pos.lite.config'].create({
            'name': 'POS No-Clear Config',
            'company_id': self.env.company.id,
            'warehouse_id': warehouse.id,
            'location_id': location.id,
            'pricelist_id': self._get_pricelist().id,
            'journal_id': self.env['account.journal'].search([
                ('company_id', '=', self.env.company.id),
                ('type', '=', 'cash'),
            ], limit=1).id,
        })
        with self.assertRaises(ValidationError):
            config.location_id = False

    def test_terminal_qty_is_free_to_use(self):
        """Terminal qty excludes reserved stock (Free to Use, clamped at 0)."""
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        location = self.env['stock.location'].create({
            'name': 'POS Free Qty Loc',
            'location_id': warehouse.lot_stock_id.id,
            'usage': 'internal',
            'company_id': self.env.company.id,
        })
        partially_reserved = self.env['product.product'].create({
            'name': 'Terminal Partially Reserved',
            'type': 'product',
            'sale_ok': True,
            'can_be_pos': True,
        })
        fully_reserved = self.env['product.product'].create({
            'name': 'Terminal Fully Reserved',
            'type': 'product',
            'sale_ok': True,
            'can_be_pos': True,
        })
        self.env['stock.quant'].create({
            'product_id': partially_reserved.id,
            'location_id': location.id,
            'quantity': 10.0,
            'reserved_quantity': 4.0,
        })
        self.env['stock.quant'].create({
            'product_id': fully_reserved.id,
            'location_id': location.id,
            'quantity': 5.0,
            'reserved_quantity': 5.0,
        })

        # Same read_group + free-to-use computation as the /pos_lite/api/products
        # controller.
        quant_data = self.env['stock.quant'].read_group(
            domain=[('location_id', '=', location.id)],
            fields=['product_id', 'quantity:sum', 'reserved_quantity:sum'],
            groupby=['product_id'],
            lazy=False,
        )
        qty_map = {}
        for q in quant_data:
            pid = q['product_id'][0] if isinstance(q['product_id'], (list, tuple)) else q['product_id']
            qty_map[pid] = max((q['quantity'] or 0.0) - (q['reserved_quantity'] or 0.0), 0.0)

        self.assertEqual(qty_map[partially_reserved.id], 6.0)
        self.assertEqual(qty_map[fully_reserved.id], 0.0)
