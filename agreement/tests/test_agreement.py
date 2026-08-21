# Copyright 2021 Ecosoft Co., Ltd (http://ecosoft.co.th)
# Copyright 2021 Sergio Teruel - Tecnativa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestAgreement(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.agreement_type = cls.env["agreement.type"].create(
            {
                "name": "Test Agreement Type",
                "domain": "purchase",
            }
        )
        cls.agreement = cls.env.ref("agreement.market1")
        cls.partner = cls.env["res.partner"].create(
            {"name": "Agreement Partner", "ref": "C-TEST-001"}
        )
        cls.other_partner = cls.env["res.partner"].create(
            {"name": "Other Partner", "ref": "X-TEST-001"}
        )

    def test_domain_selection(self):
        domain_agreement_type = self.env["agreement.type"]._domain_selection()
        domain_agreement = self.env["agreement"]._domain_selection()
        self.assertEqual(domain_agreement_type, domain_agreement)

    def test_agreement_type_change(self):
        self.agreement.write({"agreement_type_id": self.agreement_type.id})
        self.assertEqual(self.agreement.domain, self.agreement_type.domain)

    def test_compute_display_name(self):
        display_name = self.agreement.display_name
        self.assertEqual(display_name, f"[{self.agreement.code}] {self.agreement.name}")

    def test_copy(self):
        agreement1 = self.agreement.copy(default={"code": "Test Code"})
        agreement2 = self.agreement.copy()
        self.assertEqual(agreement1.code, "Test Code")
        self.assertNotEqual(agreement2.code, self.agreement.code)
        self.assertTrue(agreement2.code.startswith("AGR/"))

    def test_code_is_generated_automatically(self):
        agreement = self.env["agreement"].create({"name": "Generated Code Test"})
        self.assertRegex(agreement.code, r"^AGR/\d{4}/\d{2}/\d{4}$")

    def test_partner_code_syncs_in_both_directions(self):
        agreement = self.env["agreement"].new({"code": "AGR-TEST", "name": "Test"})
        agreement.partner_id = self.partner
        agreement._onchange_partner_id_partner_code()
        self.assertEqual(agreement.partner_code, "C-TEST-001")

        agreement.partner_id = False
        agreement.partner_code = "C-TEST-001"
        agreement._onchange_partner_code_partner_id()
        self.assertEqual(agreement.partner_id, self.partner)

    def test_partner_code_must_start_with_c_and_match_partner(self):
        with self.assertRaises(ValidationError):
            self.env["agreement"].create(
                {
                    "code": "AGR-BAD",
                    "name": "Invalid",
                    "partner_id": self.partner.id,
                    "partner_code": "X-TEST-001",
                }
            )
        with self.assertRaises(ValidationError):
            self.env["agreement"].create(
                {
                    "code": "AGR-MISMATCH",
                    "name": "Mismatch",
                    "partner_id": self.partner.id,
                    "partner_code": "C-OTHER-001",
                }
            )

    def test_partner_code_autocomplete_filters_by_ref(self):
        Partner = self.env["res.partner"].with_context(agreement_partner_code=True)
        result = Partner.name_search()
        result_ids = {partner_id for partner_id, _name in result}
        self.assertIn(self.partner.id, result_ids)
        self.assertNotIn(self.other_partner.id, result_ids)

        result = Partner.name_search("TEST-001")
        self.assertEqual(result, [(self.partner.id, "C-TEST-001")])
