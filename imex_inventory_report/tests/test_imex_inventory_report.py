from odoo.tests import TransactionCase


class TestImexInventoryReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.location_stock = cls.env.ref("stock.stock_location_stock")
        cls.location_production = cls.env["stock.location"].search(
            [("usage", "=", "production")],
            limit=1,
        )
        if not cls.location_production:
            cls.location_production = cls.env["stock.location"].create({
                "name": "Test Production",
                "usage": "production",
            })

        cls.product = cls.env["product.product"].create({
            "name": "IMEX Partial Done Product",
            "default_code": "IMEX-PARTIAL-DONE",
            "type": "product",
            "uom_id": cls.uom_unit.id,
            "uom_po_id": cls.uom_unit.id,
        })
        cls.report_date = "2026-05-11 07:43:36"
        cls.reference = "IMEX/PARTIAL/0001"

    def _create_wizard(self, is_groupby_location):
        return self.env["imex.inventory.report.wizard"].create({
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
            "product_ids": [(6, 0, [self.product.id])],
            "is_groupby_location": is_groupby_location,
        })

    def _create_partial_done_move(self):
        move = self.env["stock.move"].create({
            "name": self.reference,
            "company_id": self.env.company.id,
            "product_id": self.product.id,
            "product_uom": self.uom_unit.id,
            "product_uom_qty": 4.0,
            "location_id": self.location_stock.id,
            "location_dest_id": self.location_production.id,
            "reference": self.reference,
        })
        self.env["stock.move.line"].create({
            "move_id": move.id,
            "company_id": self.env.company.id,
            "product_id": self.product.id,
            "product_uom_id": self.uom_unit.id,
            "quantity": 2.0,
            "quantity_product_uom": 2.0,
            "location_id": self.location_stock.id,
            "location_dest_id": self.location_production.id,
            "reference": self.reference,
            "date": self.report_date,
        })
        move.write({
            "state": "done",
            "date": self.report_date,
        })
        self.env.cr.execute(
            "UPDATE stock_move SET quantity = %s WHERE id = %s",
            (2.0, move.id),
        )
        self.env.invalidate_all()
        return self.env["stock.move"].browse(move.id)

    def _create_done_move(self, source, destination, quantity, date, reference):
        move = self.env["stock.move"].create({
            "name": reference,
            "company_id": self.env.company.id,
            "product_id": self.product.id,
            "product_uom": self.uom_unit.id,
            "product_uom_qty": quantity,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "reference": reference,
        })
        self.env["stock.move.line"].create({
            "move_id": move.id,
            "company_id": self.env.company.id,
            "product_id": self.product.id,
            "product_uom_id": self.uom_unit.id,
            "quantity": quantity,
            "quantity_product_uom": quantity,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "reference": reference,
            "date": date,
        })
        move.write({
            "state": "done",
            "date": date,
        })
        self.env.cr.execute(
            "UPDATE stock_move SET quantity = %s WHERE id = %s",
            (quantity, move.id),
        )
        self.env.invalidate_all()
        return self.env["stock.move"].browse(move.id)

    def test_summary_initial_subtracts_outbound_external_moves(self):
        self._create_done_move(
            self.location_production,
            self.location_stock,
            5.0,
            "2026-04-01 08:00:00",
            "IMEX/OPENING/IN",
        )
        self._create_done_move(
            self.location_stock,
            self.location_production,
            2.0,
            "2026-04-02 08:00:00",
            "IMEX/OPENING/OUT",
        )
        wizard = self._create_wizard(is_groupby_location=True)

        self.env["imex.inventory.report"].init_results(wizard)
        report_line = self.env["imex.inventory.report"].search(
            [
                ("product_id", "=", self.product.id),
                ("location", "=", self.location_stock.id),
            ],
            limit=1,
        )

        self.assertTrue(report_line, "Expected report line for stock location")
        self.assertEqual(report_line.initial, 3.0)

    def test_summary_report_uses_done_quantity(self):
        self._create_partial_done_move()
        wizard = self._create_wizard(is_groupby_location=False)

        self.env["imex.inventory.report"].init_results(wizard)
        report_line = self.env["imex.inventory.report"].search(
            [("product_id", "=", self.product.id)],
            limit=1,
        )

        self.assertTrue(report_line, "Expected report line for test product")
        self.assertEqual(report_line.product_out, 2.0)
        self.assertEqual(report_line.balance, -2.0)

    def test_detail_report_uses_done_quantity(self):
        self._create_partial_done_move()
        wizard = self._create_wizard(is_groupby_location=True)

        self.env["imex.inventory.details.report"].init_results(wizard)
        report_line = self.env["imex.inventory.details.report"].search(
            [("product_id", "=", self.product.id), ("reference", "=", self.reference)],
            limit=1,
        )

        self.assertTrue(report_line, "Expected detail line for test product")
        self.assertEqual(report_line.product_qty, 2.0)
        self.assertEqual(report_line.product_out, 2.0)

    def test_report_details_without_filters_context(self):
        self._create_partial_done_move()
        wizard = self._create_wizard(is_groupby_location=True)
        self.env["imex.inventory.report"].init_results(wizard)
        report_line = self.env["imex.inventory.report"].search(
            [("product_id", "=", self.product.id)],
            limit=1,
        )
        self.assertTrue(report_line, "Expected report line for test product")

        action = report_line.with_context(filters=None).report_details()

        self.assertEqual(action["type"], "ir.actions.report")
        self.assertEqual(
            action["report_name"],
            "imex_inventory_report.imex_inventory_details_report_html",
        )
