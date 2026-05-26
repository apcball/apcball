from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestBOReportExcel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Requisition = cls.env["purchase.requisition"]
        cls.Wizard = cls.env["bo.report.excel.wizard"]

        # Ensure agreement type exists
        cls.agreement_type = cls.env["purchase.requisition.type"].search(
            [], limit=1
        )
        if not cls.agreement_type:
            cls.agreement_type = cls.env["purchase.requisition.type"].create({
                "name": "Test BO Type",
                "quantity_copy": "none",
                "line_copy": "copy",
            })

        cls.vendor = cls.env["res.partner"].create({
            "name": "Test Vendor BOReport",
            "supplier_rank": 1,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Test Product BOReport",
            "purchase_ok": True,
            "list_price": 100.0,
        })

    def _create_requisition(self, **kwargs):
        vals = {
            "vendor_id": self.vendor.id,
            "type_id": self.agreement_type.id,
            "ordering_date": "2025-01-15",
            "state": "draft",
            "line_ids": [(0, 0, {
                "product_id": self.product.id,
                "product_qty": 10.0,
                "price_unit": 100.0,
            })],
        }
        vals.update(kwargs)
        return self.Requisition.create(vals)

    # ── Test wizard creation ───────────────────────────────────
    def test_wizard_create(self):
        wizard = self.Wizard.create({
            "date_from": "2025-01-01",
            "date_to": "2025-12-31",
        })
        self.assertTrue(wizard.id)
        self.assertEqual(wizard.date_from.strftime("%Y-%m-%d"), "2025-01-01")

    # ── Test domain without filters ────────────────────────────
    def test_domain_no_filters(self):
        wizard = self.Wizard.create({})
        domain = wizard._get_requisition_domain()
        self.assertEqual(domain, [])

    # ── Test domain with all filters ───────────────────────────
    def test_domain_with_filters(self):
        wizard = self.Wizard.create({
            "date_from": "2025-01-01",
            "date_to": "2025-12-31",
            "vendor_id": self.vendor.id,
            "state": "draft",
        })
        domain = wizard._get_requisition_domain()
        self.assertIn(("ordering_date", ">=", wizard.date_from), domain)
        self.assertIn(("ordering_date", "<=", wizard.date_to), domain)
        self.assertIn(("vendor_id", "=", self.vendor.id), domain)
        self.assertIn(("state", "=", "draft"), domain)

    # ── Test domain with pre-selected requisitions ─────────────
    def test_domain_with_requisition_ids(self):
        req = self._create_requisition()
        wizard = self.Wizard.create({
            "requisition_ids": [(6, 0, [req.id])],
        })
        domain = wizard._get_requisition_domain()
        self.assertIn(("id", "in", [req.id]), domain)

    # ── Test export produces xlsx ──────────────────────────────
    def test_export_excel(self):
        req = self._create_requisition()
        wizard = self.Wizard.create({
            "requisition_ids": [(6, 0, [req.id])],
        })
        result = wizard.action_export_excel()
        self.assertEqual(result["type"], "ir.actions.act_url")
        self.assertIn("/web/content/", result["url"])
        self.assertIn("download=true", result["url"])

        # Verify attachment was created with xlsx content
        attachment = self.env["ir.attachment"].search([
            ("res_model", "=", "bo.report.excel.wizard"),
            ("res_id", "=", wizard.id),
        ], limit=1)
        self.assertTrue(attachment, "Attachment should be created")
        self.assertEqual(
            attachment.mimetype,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # ── Test export no data raises error ───────────────────────
    def test_export_no_data(self):
        wizard = self.Wizard.create({
            "date_from": "2099-01-01",
            "date_to": "2099-12-31",
        })
        with self.assertRaises(Exception):
            wizard.action_export_excel()
