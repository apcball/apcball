from base64 import b64encode
from datetime import date

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
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

    def test_requester_only_sees_own_assets_and_cannot_write(self):
        own = self.env["buz.it.asset"].sudo().create({"asset_name": "Own", "category_id": self.category.id, "assigned_user_id": self.requester.id})
        other = self.env["buz.it.asset"].sudo().create({"asset_name": "Other", "category_id": self.category.id, "assigned_user_id": self.agent.id})
        assets = self.env["buz.it.asset"].with_user(self.requester).search([("id", "in", [own.id, other.id])])
        self.assertEqual(assets.ids, [own.id])
        with self.assertRaises(AccessError):
            own.with_user(self.requester).write({"notes": "not allowed"})

