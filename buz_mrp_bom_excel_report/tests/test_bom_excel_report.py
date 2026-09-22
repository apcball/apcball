import io
import zipfile

from odoo import Command
from odoo.tests.common import TransactionCase


class TestBomExcelReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.env["report.buz_mrp_bom_excel_report.bom_excel_xlsx"]
        cls.product_model = cls.env["product.product"]
        cls.uom = cls.env.ref("uom.product_uom_unit")

    def _create_bom(self, bom_type, with_component=True):
        parent = self.product_model.create({"name": "BOM Excel Parent"})
        values = {
            "product_tmpl_id": parent.product_tmpl_id.id,
            "type": bom_type,
        }
        if with_component:
            component = self.product_model.create({"name": "BOM Excel Component"})
            values["bom_line_ids"] = [
                Command.create({
                    "product_id": component.id,
                    "product_qty": 1,
                    "product_uom_id": self.uom.id,
                }),
                Command.create({
                    "product_id": component.id,
                    "product_qty": 2,
                    "product_uom_id": self.uom.id,
                }),
            ]
        return self.env["mrp.bom"].create(values)

    def _expected_bom_type_label(self, bom):
        field = bom._fields["type"]
        return dict(field._description_selection(self.env))[bom.type]

    def test_bom_type_label_is_repeated_for_component_rows(self):
        for bom_type in ("normal", "phantom"):
            with self.subTest(bom_type=bom_type):
                bom = self._create_bom(bom_type)
                rows = self.report._prepare_rows(bom)

                self.assertEqual(len(rows), 2)
                self.assertEqual(
                    {row["bom_type"] for row in rows},
                    {self._expected_bom_type_label(bom)},
                )
                self.assertNotIn(
                    rows[0]["bom_type"],
                    {"Storable Product", "Consumable", "Service"},
                )

    def test_bom_type_label_is_present_without_components(self):
        bom = self._create_bom("phantom", with_component=False)

        rows = self.report._prepare_rows(bom)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["bom_type"], self._expected_bom_type_label(bom))

    def test_generated_workbook_contains_bom_type_label(self):
        import xlsxwriter

        bom = self._create_bom("phantom")
        stream = io.BytesIO()
        workbook = xlsxwriter.Workbook(stream, {"in_memory": True})

        self.report.generate_xlsx_report(
            workbook,
            {},
            bom,
        )
        workbook.close()

        with zipfile.ZipFile(stream) as archive:
            shared_strings = archive.read("xl/sharedStrings.xml")

        expected_label = self._expected_bom_type_label(bom).encode()
        self.assertIn(expected_label, shared_strings)
        self.assertNotIn(b"Storable Product", shared_strings)
        self.assertNotIn(b"Consumable", shared_strings)
