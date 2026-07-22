from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.tests.common import TransactionCase


class TestWarrantyPeriod(TransactionCase):
    def setUp(self):
        super().setUp()
        self.category = self.env['product.category'].create({
            'name': 'Warranty Test Category',
            'warranty_duration': 18,
            'warranty_period_unit': 'month',
        })
        self.product = self.env['product.template'].create({
            'name': 'Warranty Test Product',
            'categ_id': self.category.id,
        })

    def test_product_inherits_category_period_without_override(self):
        self.assertFalse(self.product.warranty_duration_override)
        self.assertEqual(self.product.warranty_duration, 18)
        self.assertEqual(self.product.warranty_period_unit, 'month')

    def test_product_override_takes_precedence_over_category(self):
        self.product.write({
            'warranty_duration_override': 2,
            'warranty_period_unit_override': 'year',
        })
        self.category.write({
            'warranty_duration': 24,
            'warranty_period_unit': 'month',
        })

        self.assertEqual(self.product.warranty_duration, 2)
        self.assertEqual(self.product.warranty_period_unit, 'year')

    def test_disabling_product_override_restores_category_period(self):
        self.product.write({
            'warranty_duration_override': 2,
            'warranty_period_unit_override': 'year',
        })
        self.product.write({'warranty_duration_override': 0})

        self.assertEqual(self.product.warranty_duration, 18)
        self.assertEqual(self.product.warranty_period_unit, 'month')

    def test_card_snapshots_month_period_and_is_unchanged_by_configuration(self):
        start_date = date(2026, 1, 31)
        card = self._create_card(start_date)

        self.assertEqual(card.warranty_duration, 18)
        self.assertEqual(card.warranty_period_unit, 'month')
        self.assertEqual(card.end_date, start_date + relativedelta(months=18))

        self.category.write({'warranty_duration': 6, 'warranty_period_unit': 'year'})
        self.product.write({
            'warranty_duration_override': 3,
            'warranty_period_unit_override': 'year',
        })
        card.invalidate_recordset()

        self.assertEqual(card.warranty_duration, 18)
        self.assertEqual(card.warranty_period_unit, 'month')
        self.assertEqual(card.end_date, start_date + relativedelta(months=18))

    def test_card_snapshots_year_period(self):
        self.product.write({
            'warranty_duration_override': 2,
            'warranty_period_unit_override': 'year',
        })
        start_date = date(2024, 2, 29)
        card = self._create_card(start_date)

        self.assertEqual(card.warranty_duration, 2)
        self.assertEqual(card.warranty_period_unit, 'year')
        self.assertEqual(card.end_date, start_date + relativedelta(years=2))

    def test_card_without_product_warranty_has_no_end_date(self):
        self.category.write({'warranty_duration': 0})

        card = self._create_card(date(2026, 1, 31))

        self.assertFalse(card.warranty_duration)
        self.assertFalse(card.warranty_period_unit)
        self.assertFalse(card.end_date)

    def test_onchange_product_uses_effective_product_period(self):
        other_category = self.env['product.category'].create({
            'name': 'Other Warranty Category',
            'warranty_duration': 3,
            'warranty_period_unit': 'month',
        })
        other_product = self.env['product.template'].create({
            'name': 'Other Warranty Product',
            'categ_id': other_category.id,
            'warranty_duration_override': 2,
            'warranty_period_unit_override': 'year',
        })
        card = self.env['warranty.card'].new({
            'partner_id': self.env['res.partner'].create({
                'name': 'Onchange Customer',
            }).id,
            'product_id': self.product.product_variant_id.id,
        })

        card._onchange_product_id()
        self.assertEqual(card.warranty_duration, 18)
        self.assertEqual(card.warranty_period_unit, 'month')

        card.product_id = other_product.product_variant_id
        card._onchange_product_id()
        self.assertEqual(card.warranty_duration, 2)
        self.assertEqual(card.warranty_period_unit, 'year')

    def test_changing_product_resnapshots_warranty_period(self):
        other_category = self.env['product.category'].create({
            'name': 'Changed Product Category',
            'warranty_duration': 3,
            'warranty_period_unit': 'month',
        })
        other_product = self.env['product.template'].create({
            'name': 'Changed Warranty Product',
            'categ_id': other_category.id,
            'warranty_duration_override': 2,
            'warranty_period_unit_override': 'year',
        })
        card = self._create_card(date(2026, 1, 31))

        card.write({'product_id': other_product.product_variant_id.id})

        self.assertEqual(card.warranty_duration, 2)
        self.assertEqual(card.warranty_period_unit, 'year')
        self.assertEqual(card.end_date, date(2028, 1, 31))

    def test_sale_order_skips_product_without_warranty(self):
        self.category.write({'warranty_duration': 0})
        partner = self.env['res.partner'].create({'name': 'Sale Customer'})
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [Command.create({
                'name': self.product.name,
                'product_id': self.product.product_variant_id.id,
                'product_uom_qty': 1,
                'product_uom': self.product.uom_id.id,
                'price_unit': 10,
            })],
        })
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': partner.property_stock_customer.id,
            'partner_id': partner.id,
            'state': 'done',
        })
        move_line = self.env['stock.move.line'].create({
            'picking_id': picking.id,
            'product_id': self.product.product_variant_id.id,
            'product_uom_id': self.product.uom_id.id,
            'quantity': 1,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
        })

        order._create_warranty_cards_from_pickings(picking)

        self.assertFalse(self.env['warranty.card'].search([
            ('picking_id', '=', picking.id),
            ('product_id', '=', self.product.product_variant_id.id),
        ]))

    def _create_card(self, start_date):
        return self.env['warranty.card'].create({
            'partner_id': self.env['res.partner'].create({
                'name': 'Warranty Test Customer',
            }).id,
            'product_id': self.product.product_variant_id.id,
            'start_date': start_date,
        })
