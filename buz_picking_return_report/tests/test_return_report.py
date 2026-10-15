from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPickingReturnReport(TransactionCase):
    def _done_out_picking(self):
        wh = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        product = self.env["product.product"].create(
            {"name": "RetRpt Prod", "type": "product"}
        )
        self.env["stock.quant"]._update_available_quantity(
            product, wh.lot_stock_id, 10
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": wh.out_type_id.id,
                "location_id": wh.lot_stock_id.id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                "move_ids": [
                    (0, 0, {
                        "name": product.name,
                        "product_id": product.id,
                        "product_uom_qty": 5,
                        "product_uom": product.uom_id.id,
                        "location_id": wh.lot_stock_id.id,
                        "location_dest_id": self.env.ref(
                            "stock.stock_location_customers"
                        ).id,
                    })
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = 5
        picking.button_validate()
        return picking

    def _return(self, picking):
        wiz = self.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking"
        ).create({"picking_id": picking.id})
        new_id, _ = wiz._create_returns()
        return self.env["stock.picking"].browse(new_id)

    def test_ready_return_included_draft_cancel_excluded(self):
        picking = self._done_out_picking()
        ret = self._return(picking)
        wiz = self.env["buz.picking.return.report.wizard"].create({})
        self.assertIn(ret, wiz._get_return_moves().picking_id)  # ready
        ret.action_cancel()
        self.assertNotIn(ret, wiz._get_return_moves().picking_id)

    def test_outside_period_excluded(self):
        picking = self._done_out_picking()
        ret = self._return(picking)
        wiz = self.env["buz.picking.return.report.wizard"].create(
            {"date_from": "2000-01-01", "date_to": "2000-01-31"}
        )
        self.assertNotIn(ret, wiz._get_return_moves().picking_id)

    def test_export_returns_attachment(self):
        picking = self._done_out_picking()
        self._return(picking)
        wiz = self.env["buz.picking.return.report.wizard"].create({})
        res = wiz.action_export_xlsx()
        self.assertEqual(res["type"], "ir.actions.act_url")
