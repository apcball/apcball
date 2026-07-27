from base64 import b64encode
from datetime import date

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestItAsset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other_company = cls.env["res.company"].sudo().create({"name": "IT Asset Test Company"})
        cls.category = cls.env.ref("buz_it_helpdesk.asset_category_laptop")
        cls.requester_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_requester")
        cls.agent_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_agent")
        cls.manager_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_manager")

        def user(login, name, group):
            return cls.env["res.users"].sudo().create({
                "name": name,
                "login": login,
                "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, group.id])],
            })

        cls.requester = user("asset.requester", "Asset Requester", cls.requester_group)
        cls.agent = user("asset.agent", "Asset Agent", cls.agent_group)
        cls.manager = user("asset.manager", "Asset Manager", cls.manager_group)

    def test_sequence_and_assignment_default(self):
        asset = self.env["buz.it.asset"].with_user(self.agent).create({
            "asset_name": "Assigned laptop",
            "category_id": self.category.id,
            "assigned_user_id": self.requester.id,
            "user_nickname": "Jo",
            "computer_username": "jdoe",
        })
        self.assertRegex(asset.name, r"^ITA/\d{4}/\d{4}$")
        self.assertEqual(asset.status, "in_use")
        self.assertEqual(asset.user_nickname, "Jo")
        self.assertEqual(asset.computer_username, "jdoe")

    def test_asset_types_and_assignment_clearing(self):
        model = self.env["buz.it.asset"].with_user(self.agent)
        asset = model.create({
            "asset_name": "Email account",
            "asset_type": "email",
            "service_name": "Microsoft 365",
            "account_email": "user@example.com",
            "assigned_user_id": self.requester.id,
        })
        self.assertEqual(asset.asset_type, "email")
        self.assertEqual(asset.status, "in_use")
        asset.write({"assigned_user_id": False})
        self.assertFalse(asset.assigned_user_id)
        self.assertEqual(asset.status, "available")

    def test_asset_specification_values(self):
        categories = {
            "CPU": self.env.ref("buz_it_helpdesk.asset_spec_category_cpu"),
            "RAM": self.env.ref("buz_it_helpdesk.asset_spec_category_ram"),
            "GPU": self.env.ref("buz_it_helpdesk.asset_spec_category_gpu"),
            "Storage": self.env.ref("buz_it_helpdesk.asset_spec_category_storage"),
        }
        expected = {
            "CPU": "Intel Core i7",
            "RAM": "32 GB",
            "GPU": "RTX 4060",
            "Storage": "1 TB NVMe",
        }
        asset = self.env["buz.it.asset"].with_user(self.agent).create({
            "asset_name": "Specification test",
            "category_id": self.category.id,
            "spec_line_ids": [
                fields.Command.create({"category_id": categories[name].id, "value": value})
                for name, value in expected.items()
            ],
        })
        self.assertEqual(
            {line.category_id.name: line.value for line in asset.spec_line_ids},
            expected,
        )

    def test_asset_file_attachment(self):
        asset = self.env["buz.it.asset"].with_user(self.agent).create({
            "asset_name": "Asset with attachment",
            "category_id": self.category.id,
        })
        attachment = self.env["ir.attachment"].sudo().create({
            "name": "asset-manual.pdf",
            "datas": b64encode(b"%PDF-1.4 test attachment"),
            "mimetype": "application/pdf",
            "res_model": asset._name,
            "res_id": asset.id,
        })
        asset.with_user(self.agent).write({
            "attachment_ids": [fields.Command.link(attachment.id)],
        })
        self.assertEqual(asset.attachment_ids, attachment)

    def test_status_and_warranty_constraints(self):
        vals = {"asset_name": "Test device", "category_id": self.category.id}
        with self.assertRaises(ValidationError):
            self.env["buz.it.asset"].with_user(self.agent).create(dict(vals, status="in_use"))
        with self.assertRaises(ValidationError):
            self.env["buz.it.asset"].with_user(self.agent).create(dict(vals, purchase_date=date(2026, 2, 1), warranty_expiry_date=date(2026, 1, 1)))

    def test_serial_unique_per_company(self):
        model = self.env["buz.it.asset"].with_user(self.agent)
        model.create({"asset_name": "Device A", "category_id": self.category.id, "serial_number": "SERIAL-1"})
        with self.assertRaises(Exception):
            model.create({"asset_name": "Device B", "category_id": self.category.id, "serial_number": "SERIAL-1"})
        model.sudo().with_company(self.other_company).create({"asset_name": "Device Other Company", "category_id": self.category.id, "serial_number": "SERIAL-1", "company_id": self.other_company.id})

    def test_requester_cannot_access_assets(self):
        self.env["buz.it.asset"].sudo().create({
            "asset_name": "Restricted Asset",
            "category_id": self.category.id,
            "assigned_user_id": self.requester.id,
        })
        with self.assertRaises(AccessError):
            self.env["buz.it.asset"].with_user(self.requester).search([])
    def test_phase_5a_role_matrix_and_license_key_boundary(self):
        asset_user_group = self.env.ref("buz_it_helpdesk.group_it_asset_user")
        asset_manager_group = self.env.ref("buz_it_helpdesk.group_it_asset_manager")
        asset_user = self.env["res.users"].sudo().create({
            "name": "IT Asset User",
            "login": "it.asset.user.5a",
            "groups_id": [fields.Command.set([self.env.ref("base.group_user").id, asset_user_group.id])],
        })
        asset_manager = self.env["res.users"].sudo().create({
            "name": "IT Asset Manager",
            "login": "it.asset.manager.5a",
            "groups_id": [fields.Command.set([self.env.ref("base.group_user").id, asset_manager_group.id])],
        })
        asset = self.env["buz.it.asset"].with_user(asset_manager).create({
            "asset_name": "Role matrix license",
            "asset_type": "software_license",
            "license_product": "Product",
            "license_key": "SECRET-5A",
        })
        self.assertEqual(asset.with_user(asset_manager).license_key, "SECRET-5A")
        with self.assertRaises(AccessError):
            asset.with_user(asset_user).read(["license_key"])
        asset.with_user(asset_user).write({"asset_name": "Role matrix license updated"})

    def test_phase_5a_company_rule_and_archive_instead_of_delete(self):
        asset = self.env["buz.it.asset"].with_user(self.agent).create({
            "asset_name": "Company boundary asset",
            "company_id": self.company.id,
        })
        other_asset = self.env["buz.it.asset"].sudo().with_company(self.other_company).create({
            "asset_name": "Other company asset",
            "company_id": self.other_company.id,
        })
        visible_other = self.env["buz.it.asset"].with_user(self.agent).with_company(self.other_company).search([])
        self.assertNotIn(other_asset.id, visible_other.ids)
        with self.assertRaises(UserError):
            asset.with_user(self.manager).unlink()
        asset.with_user(self.manager).write({"active": False})
        self.assertFalse(asset.active)
    def test_phase_5a_portal_user_cannot_access_assets(self):
        portal_user = self.env["res.users"].sudo().create({
            "name": "Asset Portal User",
            "login": "asset.portal.user.5a",
            "groups_id": [fields.Command.set([self.env.ref("base.group_portal").id])],
        })
        with self.assertRaises(AccessError):
            self.env["buz.it.asset"].with_user(portal_user).search([])