import io
import zipfile

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestBomExcelReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.env["report.buz_mrp_bom_excel_report.bom_excel_xlsx"]
        cls.product_model = cls.env["product.product"]
        cls.uom = cls.env.ref("uom.product_uom_unit")

    def _create_bom(
        self,
        bom_type,
        with_component=True,
        reference=None,
        component_count=2,
    ):
        parent = self.product_model.create({
            "name": "BOM Excel Parent",
            "default_code": "BOM-PARENT-001",
        })
        values = {
            "product_tmpl_id": parent.product_tmpl_id.id,
            "type": bom_type,
        }
        if reference is not None:
            values["code"] = reference
        if with_component:
            values["bom_line_ids"] = []
            for index in range(component_count):
                component = self.product_model.create({
                    "name": f"BOM Excel Component {index + 1}",
                })
                values["bom_line_ids"].append(Command.create({
                    "product_id": component.id,
                    "product_qty": index + 1,
                    "product_uom_id": self.uom.id,
                }))
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

    def test_parent_values_are_shown_only_on_first_component_row(self):
        bom = self._create_bom(
            "normal",
            reference="BOM-REF-001",
            component_count=3,
        )

        rows = self.report._prepare_rows(bom)

        self.assertEqual(len(rows), 3)
        self.assertNotEqual(rows[0]["product_code"], "")
        self.assertNotEqual(rows[0]["product_name"], "")
        self.assertEqual(rows[0]["bom_name"], "BOM-REF-001")
        for row in rows[1:]:
            self.assertEqual(row["product_code"], "")
            self.assertEqual(row["product_name"], "")
            self.assertEqual(row["bom_name"], "")

    def test_each_bom_starts_a_new_parent_value_group(self):
        first_bom = self._create_bom("normal", reference="BOM-REF-001")
        second_bom = self._create_bom("phantom", reference="BOM-REF-002")

        rows = self.report._prepare_rows(first_bom | second_bom)

        self.assertEqual(len(rows), 4)
        self.assertEqual(
            [row["bom_name"] for row in rows],
            ["BOM-REF-001", "", "BOM-REF-002", ""],
        )

    def test_bom_report_action_is_bound_to_bom_action_menu(self):
        action = self.env.ref(
            "buz_mrp_bom_excel_report.action_bom_excel_selected_report"
        )

        self.assertEqual(action.binding_model_id.model, "mrp.bom")
        self.assertEqual(action.binding_type, "action")
        self.assertEqual(
            action.report_name,
            "buz_mrp_bom_excel_report.bom_excel_selected_xlsx",
        )
        self.assertNotEqual(
            action.report_name,
            self.env.ref(
                "buz_mrp_bom_excel_report.action_bom_excel_report"
            ).report_name,
        )

    def test_selected_boms_are_used_for_export(self):
        first_bom = self._create_bom("normal", reference="BOM-REF-001")
        second_bom = self._create_bom("phantom", reference="BOM-REF-002")

        selected = self.report._get_boms(second_bom)

        self.assertEqual(selected.ids, [second_bom.id])
        self.assertNotIn(first_bom.id, selected.ids)

    def test_active_ids_are_used_when_report_records_are_not_boms(self):
        first_bom = self._create_bom("normal", reference="BOM-REF-001")
        second_bom = self._create_bom("phantom", reference="BOM-REF-002")
        wizard = self.env["buz.mrp.bom.excel.wizard"].create({})

        selected = self.report._selected_boms(
            wizard,
            {
                "context": {
                    "active_model": "mrp.bom",
                    "active_ids": [second_bom.id],
                },
            },
        )

        self.assertEqual(selected.ids, [second_bom.id])
        self.assertNotIn(first_bom.id, selected.ids)

    def test_no_active_ids_falls_back_to_all_boms(self):
        wizard = self.env["buz.mrp.bom.excel.wizard"].create({})

        selected = self.report._selected_boms(wizard, {"context": {}})

        self.assertIsNone(selected)

    def test_selected_report_writes_only_selected_bom(self):
        first_bom = self._create_bom("normal", reference="BOM-REF-001")
        second_bom = self._create_bom("phantom", reference="BOM-REF-002")
        selected_report = self.env[
            "report.buz_mrp_bom_excel_report.bom_excel_selected_xlsx"
        ].with_context(active_model="mrp.bom")

        content, file_type = selected_report.create_xlsx_report(
            [second_bom.id], {}
        )

        self.assertEqual(file_type, "xlsx")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            shared_strings = archive.read("xl/sharedStrings.xml").decode()
        self.assertIn("BOM-REF-002", shared_strings)
        self.assertNotIn("BOM-REF-001", shared_strings)
        self.assertNotEqual(first_bom.id, second_bom.id)

    def test_selected_report_writes_only_multiple_selected_boms(self):
        selected_boms = self.env["mrp.bom"]
        self._create_bom("normal", reference="BOM-UNSELECTED")
        for index in range(80):
            selected_boms |= self._create_bom(
                "normal", reference=f"BOM-SELECTED-{index + 1:03d}"
            )

        selected_report = self.env[
            "report.buz_mrp_bom_excel_report.bom_excel_selected_xlsx"
        ]
        content, file_type = selected_report.create_xlsx_report(
            selected_boms.ids, {}
        )

        self.assertEqual(file_type, "xlsx")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            shared_strings = archive.read("xl/sharedStrings.xml").decode()
        for index in range(80):
            self.assertIn(f"BOM-SELECTED-{index + 1:03d}", shared_strings)
        self.assertNotIn("BOM-UNSELECTED", shared_strings)

    def test_selected_report_rejects_empty_selection(self):
        selected_report = self.env[
            "report.buz_mrp_bom_excel_report.bom_excel_selected_xlsx"
        ]

        with self.assertRaisesRegex(UserError, "กรุณาเลือกรายการ BOM"):
            selected_report.create_xlsx_report([], {})

    def test_no_selection_returns_accessible_boms(self):
        first_bom = self._create_bom("normal", reference="BOM-REF-001")
        second_bom = self._create_bom("phantom", reference="BOM-REF-002")

        all_boms = self.report._get_boms()

        self.assertIn(first_bom.id, all_boms.ids)
        self.assertIn(second_bom.id, all_boms.ids)

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

    def test_reference_is_used_for_bom_name(self):
        bom = self._create_bom("normal", reference="BOM-REF-001")

        rows = self.report._prepare_rows(bom)

        self.assertEqual(
            [row["bom_name"] for row in rows],
            ["BOM-REF-001", ""],
        )
        self.assertNotIn("BOM Excel Parent", rows[0]["bom_name"])

    def test_missing_reference_keeps_bom_name_empty(self):
        bom = self._create_bom("normal", reference=None)

        rows = self.report._prepare_rows(bom)

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["bom_name"] for row in rows}, {""})

    def test_generated_workbook_keeps_missing_reference_empty(self):
        import xlsxwriter

        bom = self._create_bom("normal", reference=None)
        stream = io.BytesIO()
        workbook = xlsxwriter.Workbook(stream, {"in_memory": True})

        self.report.generate_xlsx_report(workbook, {}, bom)
        workbook.close()

        with zipfile.ZipFile(stream) as archive:
            worksheet = archive.read("xl/worksheets/sheet1.xml").decode()

        self.assertIn('r="C3"', worksheet)
        self.assertNotIn("BOM Excel Parent", worksheet)

    def test_generated_workbook_does_not_repeat_parent_values(self):
        import xlsxwriter

        bom = self._create_bom(
            "normal",
            reference="BOM-REF-001",
            component_count=3,
        )
        stream = io.BytesIO()
        workbook = xlsxwriter.Workbook(stream, {"in_memory": True})

        self.report.generate_xlsx_report(workbook, {}, bom)
        workbook.close()

        with zipfile.ZipFile(stream) as archive:
            worksheet = archive.read("xl/worksheets/sheet1.xml").decode()

        self.assertEqual(worksheet.count('r="C3"'), 1)
        self.assertIn('<c r="C4" s="3"/>', worksheet)
        self.assertIn('<c r="C5" s="3"/>', worksheet)
