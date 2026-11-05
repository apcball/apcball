from odoo import fields
from odoo.tests.common import TransactionCase


class TestStockPickingAnalyticSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.product = cls.env["product.product"].create(
            {"name": "Analytic Sync Test Product", "type": "product"}
        )
        cls.source_location = cls.env.ref("stock.stock_location_stock")
        cls.destination_location = cls.env["stock.location"].create(
            {
                "name": "Analytic Sync Test Destination",
                "usage": "internal",
                "location_id": cls.source_location.id,
                "company_id": cls.company.id,
            }
        )

    def _create_picking(self, picking_type_xmlid, analytic_auto_sync=True):
        picking_type = self.env.ref(picking_type_xmlid)
        if picking_type.code == "incoming":
            source = self.env.ref("stock.stock_location_suppliers")
            destination = self.source_location
        elif picking_type.code == "outgoing":
            source = self.source_location
            destination = self.env.ref("stock.stock_location_customers")
        else:
            source = self.source_location
            destination = self.destination_location

        move_vals = {
            "name": self.product.display_name,
            "product_id": self.product.id,
            "product_uom": self.product.uom_id.id,
            "product_uom_qty": 1,
            "location_id": source.id,
            "location_dest_id": destination.id,
        }
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "analytic_auto_sync": analytic_auto_sync,
                "move_ids_without_package": [
                    fields.Command.create(
                        {
                            **move_vals,
                            "sequence": 1,
                            "analytic_distribution": {"101": 100.0},
                        }
                    ),
                    fields.Command.create({**move_vals, "sequence": 2}),
                    fields.Command.create(
                        {
                            **move_vals,
                            "sequence": 3,
                            "analytic_distribution": {"202": 60.0},
                        }
                    ),
                ],
            }
        )
        return picking

    def test_internal_transfer_sync_fills_only_empty_moves(self):
        picking = self._create_picking("stock.picking_type_internal")

        moves = picking.move_ids_without_package.sorted(key=lambda move: move.sequence)
        self.assertEqual(moves[1].analytic_distribution, {"101": 100.0})
        self.assertEqual(moves[2].analytic_distribution, {"202": 60.0})

    def test_sync_disabled_or_non_internal_picking_does_not_copy(self):
        disabled_picking = self._create_picking(
            "stock.picking_type_internal", analytic_auto_sync=False
        )
        outgoing_picking = self._create_picking("stock.picking_type_out")

        for picking in (disabled_picking, outgoing_picking):
            moves = picking.move_ids_without_package.sorted(key=lambda move: move.sequence)
            self.assertFalse(moves[1].analytic_distribution)

    def test_enabling_sync_on_existing_internal_transfer_copies_missing_values(self):
        picking = self._create_picking(
            "stock.picking_type_internal", analytic_auto_sync=False
        )
        picking.write({"analytic_auto_sync": True})

        moves = picking.move_ids_without_package.sorted(key=lambda move: move.sequence)
        self.assertEqual(moves[1].analytic_distribution, {"101": 100.0})
