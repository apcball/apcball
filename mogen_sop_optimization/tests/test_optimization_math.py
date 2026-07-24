from odoo.tests.common import TransactionCase

from odoo.addons.mogen_sop_optimization.services.inventory_math import InventoryMath


class TestInventoryMath(TransactionCase):
    def test_safety_stock_reorder_point_and_eoq(self):
        self.assertEqual(InventoryMath.fixed_safety_stock(25.0), 25.0)
        self.assertEqual(InventoryMath.days_of_demand_safety_stock(12.0, 5.0), 60.0)
        self.assertAlmostEqual(
            InventoryMath.statistical_safety_stock(10.0, 4.0, 1.645, 9.0), 19.74
        )
        self.assertEqual(InventoryMath.reorder_point(10.0, 6.0, 25.0), 85.0)
        self.assertAlmostEqual(InventoryMath.eoq(1200.0, 25.0, 5.0), 109.5445115, places=6)

    def test_safe_zero_inputs_and_abc_xyz(self):
        self.assertEqual(InventoryMath.statistical_safety_stock(0.0, 4.0, 1.645, 0.0), 0.0)
        self.assertEqual(InventoryMath.eoq(0.0, 20.0, 5.0), 0.0)
        self.assertEqual(InventoryMath.eoq(100.0, 20.0, 0.0), 0.0)
        self.assertEqual(InventoryMath.xyz_class(0.0, 0.0, 0.5, 1.0), "Z")
        self.assertEqual(InventoryMath.xyz_class(10.0, 4.0, 0.5, 1.0), "X")
        self.assertEqual(InventoryMath.xyz_class(10.0, 7.0, 0.5, 1.0), "Y")
        self.assertEqual(InventoryMath.xyz_class(10.0, 12.0, 0.5, 1.0), "Z")
        classes = InventoryMath.abc_classes([(1, 80.0), (2, 15.0), (3, 5.0)], 80.0, 95.0)
        self.assertEqual(classes, {1: "A", 2: "B", 3: "C"})
