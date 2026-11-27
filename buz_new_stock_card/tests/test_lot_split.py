import io
import re
from collections import defaultdict
from unittest.mock import patch

import xlsxwriter

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.buz_new_stock_card.controllers.stock_card_controller import StockCardController

DATE_FROM = "2000-01-01"
DATE_TO = "2099-12-31"


@tagged("post_install", "-at_install")
class TestLotSplit(TransactionCase):
    """Lot split (FIFO lots = origin document of the valuation layers).

    Data-driven like buz_stock_po_lot_report's tests: the invariants must hold
    on whatever valuation layers the database carries, so no fixtures."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = "UTC"
        cls.env.user.groups_id = [Command.link(
            cls.env.ref("buz_new_stock_card.group_stock_card_see_value").id
        )]
        cls.engine = cls.env["buz.stock.card.report"]

    def _products_with_layers(self, limit=3):
        layers = self.env["stock.valuation.layer"].search(
            [("product_id.default_code", "!=", False), ("warehouse_id", "!=", False),
             ("quantity", "!=", 0)], limit=500,
        )
        products = layers.mapped("product_id")[:limit]
        if not products:
            self.skipTest("no valuation layers")
        return products

    def _rows(self, product):
        return self.engine.get_lot_split_rows([product.id], [], DATE_FROM, DATE_TO)

    def test_ending_lots_tie_to_valuation_layers(self):
        """Per warehouse: Σ ending lots (incl. the residual row) == Σ layers."""
        wiz = self.env["buz.po.lot.wizard"].sudo().new({
            "date_from": DATE_FROM, "date_to": DATE_TO,
            "company_id": self.env.company.id, "hide_zero": False,
        })
        _start, end_utc = wiz._utc_bounds()
        whs = wiz._report_wh_ids()
        names = {w.id: w.name for w in self.env["stock.warehouse"].with_context(
            active_test=False).search([])}
        for product in self._products_with_layers():
            layers = wiz._fetch_layers([product.id], wiz._cutoff_utc(), end_utc).get(product.id, [])
            expected = defaultdict(float)
            for _d, _i, sv in layers:
                if not whs or sv.wh_id in whs:
                    expected[names.get(sv.wh_id, "")] += sv.quantity
            ending = defaultdict(float)
            for row in self._rows(product):
                if row["row_type"] == "ending":
                    ending[row["warehouse_name"]] += row["bal_qty"]
            for wh_name, qty in expected.items():
                self.assertAlmostEqual(ending.get(wh_name, 0.0), qty, places=3,
                                       msg="%s / %s" % (product.default_code, wh_name))

    def test_opening_plus_moves_equal_ending_per_warehouse(self):
        for product in self._products_with_layers():
            opening, moves, ending = (defaultdict(float) for _ in range(3))
            opening_v, moves_v, ending_v = (defaultdict(float) for _ in range(3))
            for row in self._rows(product):
                wh = row["warehouse_name"]
                if row["row_type"] == "opening":
                    opening[wh] += row["bal_qty"]
                    opening_v[wh] += row["bal_value"]
                elif row["row_type"] == "move":
                    moves[wh] += row["qty_in"] - row["qty_out"]
                    moves_v[wh] += row["value_in"] - row["value_out"]
                else:
                    ending[wh] += row["bal_qty"]
                    ending_v[wh] += row["bal_value"]
            for wh in set(opening) | set(moves) | set(ending):
                self.assertAlmostEqual(opening[wh] + moves[wh], ending[wh], places=3,
                                       msg="qty %s / %s" % (product.default_code, wh))
                self.assertAlmostEqual(opening_v[wh] + moves_v[wh], ending_v[wh], places=1,
                                       msg="value %s / %s" % (product.default_code, wh))

    def test_move_rows_have_document_and_type(self):
        for product in self._products_with_layers():
            for row in self._rows(product):
                if row["row_type"] == "move":
                    self.assertTrue(row["doc_number"] or row["doc_type"] or row["date"])
                    self.assertTrue(row["date"])

    def test_requires_product_and_group(self):
        with self.assertRaises(ValidationError):
            self.engine.get_lot_split_rows([], [], DATE_FROM, DATE_TO)
        with self.assertRaises(ValidationError):
            self.engine.get_lot_split_rows(
                list(range(1, self.engine.MAX_LOT_SPLIT_PRODUCTS + 2)), [], DATE_FROM, DATE_TO)
        self.env.user.groups_id = [Command.unlink(
            self.env.ref("buz_new_stock_card.group_stock_card_see_value").id
        )]
        with self.assertRaises(AccessError):
            self.engine.get_lot_split_rows([1], [], DATE_FROM, DATE_TO)

    def test_xlsx_sheet_renders(self):
        rows = self._rows(self._products_with_layers(1))
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        fmts = {
            "header": workbook.add_format({"bold": True}),
            "num": workbook.add_format({"num_format": "#,##0.00"}),
            "text": workbook.add_format({}),
        }
        StockCardController._add_group_formats(workbook, fmts)
        StockCardController._write_lot_split_sheet(workbook, fmts, rows)
        workbook.close()
        self.assertTrue(output.getvalue())

    def test_format_fifo_lots_slices_a_move_over_its_lines(self):
        pieces = [["IN1", 5.0, 120.0], ["IN2", 3.0, 125.0], ["", 2.0, 99.0]]
        fmt = self.engine._format_fifo_lots
        self.assertEqual(fmt(pieces, 0.0, 8.0), "IN1 (5 @120.00), IN2 (3 @125.00)")
        self.assertEqual(fmt(pieces, 0.0, 4.0), "IN1 (4 @120.00)")
        self.assertEqual(fmt(pieces, 4.0, 10.0),
                         "IN1 (1 @120.00), IN2 (3 @125.00), อ้างอิงล็อตไม่ได้ (2)")
        # more moved than the layers explain
        self.assertEqual(fmt(pieces[:1], 0.0, 6.5),
                         "IN1 (5 @120.00), อ้างอิงล็อตไม่ได้ (1.5)")

    def test_valuation_rows_show_the_lots_cut(self):
        """Data-driven: lots only on outgoing rows, never more or less than
        the quantity issued, and adding them changes no figure."""
        found = 0
        for product in self._products_with_layers(20):
            rows = self.engine.get_product_all_locations_valuation_lines(
                product.id, DATE_FROM, DATE_TO)
            for row in rows:
                self.assertNotIn("_fifo_line", row)
                if not row["fifo_lot"]:
                    continue
                found += 1
                self.assertGreater(row["qty_out"], 0)
                cut = sum(float(q.replace(",", "")) for q in re.findall(
                    r"\((-?[\d,]+(?:\.\d+)?)(?: @[^)]*)?\)(?=, |$)", row["fifo_lot"]))
                self.assertAlmostEqual(cut, row["qty_out"], places=3, msg=row["fifo_lot"])
            with patch.object(type(self.engine), "_attach_fifo_lots", lambda self, rows, *a: [
                    r.pop("_fifo_line", None) for r in rows]):
                plain = self.engine.get_product_all_locations_valuation_lines(
                    product.id, DATE_FROM, DATE_TO)
            self.assertEqual([dict(r, fifo_lot="") for r in rows], plain)
        if not found:
            self.skipTest("no outgoing valuation layers")

    def test_empty_rows_render(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        fmts = {"header": workbook.add_format({}), "num": workbook.add_format({}),
                "text": workbook.add_format({})}
        StockCardController._add_group_formats(workbook, fmts)
        StockCardController._write_lot_split_sheet(workbook, fmts, [])
        workbook.close()
        self.assertTrue(output.getvalue())
