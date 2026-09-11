import base64
import json
from io import BytesIO

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, tagged
from odoo.tools.pdf import PdfFileWriter


@tagged("post_install", "-at_install")
class TestDocumentCenter(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.manager, cls.reader, cls.confidential = [
            env["res.users"].create({
                "name": login, "login": login, "password": login,
                "groups_id": [fields.Command.set([env.ref("base.group_user").id, env.ref("buz_document_control." + group).id])],
            }) for login, group in [
                ("bdc_test_manager", "group_document_manager"),
                ("bdc_test_reader", "group_document_user"),
                ("bdc_test_confidential", "group_document_confidential_user"),
            ]
        ]
        cls.department = env["hr.department"].create({"name": "BDC Test IT"})
        cls.department_group = env["res.groups"].create({"name": "BDC Test IT Department"})
        env["hr.employee"].create({"name": "BDC Reader", "user_id": cls.reader.id, "department_id": cls.department.id})
        cls.category = env["buz.document.category"].create({"name": "BDC Search Category"})
        pdf = PdfFileWriter()
        pdf.addBlankPage(595, 842)
        output = BytesIO()
        pdf.write(output)
        cls.pdf = base64.b64encode(output.getvalue())
        cls.documents = {}
        for level in ["general", "restricted", "confidential"]:
            doc = env["buz.document"].with_user(cls.manager).create({
                "document_no": "BDC-" + level, "name": "ระเบียบปฏิบัติงานสารสนเทศ " + level,
                "security_level": level, "department_id": cls.department.id,
                "document_type_id": env.ref("buz_document_control.document_type_qp").id,
                "category_id": cls.category.id,
                "allowed_group_ids": [fields.Command.set(cls.department_group.ids)] if level == "restricted" else [],
            })
            revision = env["buz.document.revision"].with_user(cls.manager).create({
                "document_id": doc.id, "revision": "04", "original_file": cls.pdf,
                "original_filename": "QP-ITD-01_Rev04.pdf", "effective_date": fields.Date.today(),
                "review_date": fields.Date.add(fields.Date.today(), days=12), "change_description": "Document Center test",
            })
            revision.action_publish()
            cls.documents[level] = doc

    def center(self, user, **kwargs):
        return self.env["buz.document"].with_user(user).get_document_center_data(**kwargs)

    def test_dashboard_counts_and_search_obey_record_rules(self):
        for user, levels in [(self.reader, ["general"]), (self.confidential, ["general", "confidential"]),
                             (self.manager, ["general", "restricted", "confidential"])]:
            expected = {self.documents[level].id for level in levels}
            data = self.center(user, query="BDC-")
            self.assertEqual({row["id"] for row in data["documents"]}, expected)
            self.assertEqual(data["total"], len(expected))
            self.assertEqual(data["is_manager"], user == self.manager)
            actual_accessible = self.env["buz.document"].with_user(user).search_count([("state", "not in", ["obsolete", "archived"])])
            self.assertEqual(data["counts"]["all"], actual_accessible)
            qp_count = next(row["count"] for row in data["document_types"] if row["code"] == "QP")
            self.assertEqual(qp_count, self.env["buz.document"].with_user(user).search_count([
                ("document_type_id.code", "=", "QP"), ("state", "not in", ["obsolete", "archived"])]))
            self.assertNotIn('"original_file":', json.dumps(data, default=str))
            self.assertNotIn('"preview_file":', json.dumps(data, default=str))
        for query in ["ระเบียบ", "BDC Test IT", "BDC Search Category", "04", "QP"]:
            self.assertIn(self.documents["general"].id, {r["id"] for r in self.center(self.reader, query=query)["documents"]})
        self.assertEqual(self.center(self.reader, query="BDC-restricted")["total"], 0)
        self.assertEqual(self.center(self.reader, filter_key="my_department", query="BDC-")["total"], 1)

    def test_viewer_denies_hidden_document_and_excludes_old_revisions(self):
        doc = self.documents["general"]
        old = doc.current_revision_id
        new = self.env["buz.document.revision"].with_user(self.manager).create({
            "document_id": doc.id, "revision": "05", "effective_date": fields.Date.today(),
            "original_file": self.pdf, "original_filename": "new.pdf", "change_description": "Replace current",
        })
        new.action_publish()
        data = doc.with_user(self.reader).get_document_viewer_data()
        self.assertEqual(data["current"]["id"], new.id)
        self.assertEqual([r["id"] for r in data["history"]], [new.id])
        self.assertFalse(data["access"])
        self.assertEqual(data["activity"], [])
        manager_data = doc.get_document_viewer_data()
        self.assertEqual({r["id"] for r in manager_data["history"]}, {old.id, new.id})
        with self.assertRaises(AccessError):
            self.documents["restricted"].with_user(self.reader).get_document_viewer_data()
        with self.assertRaises(AccessError):
            self.documents["restricted"].with_user(self.reader).action_document_viewer()

    def test_wizard_is_manager_only_and_does_not_replace_current(self):
        doc = self.documents["general"]
        old = doc.current_revision_id
        action = doc.action_new_revision()
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["views"], [[False, "form"]])
        wizard_model = self.env["buz.document.revision.wizard"]
        with self.assertRaises(AccessError):
            doc.with_user(self.reader).action_new_revision()
        with self.assertRaises(AccessError):
            wizard_model.with_user(self.reader).create({"document_id": doc.id, "revision": "05"})
        wizard = wizard_model.with_user(self.manager).create({
            "document_id": doc.id, "revision": "05", "effective_date": fields.Date.today(),
            "original_file": self.pdf, "original_filename": "updated.pdf", "change_description": "Test draft",
        })
        wizard.action_create_draft()
        new = self.env["buz.document.revision"].search([("document_id", "=", doc.id), ("revision", "=", "05")])
        self.assertEqual(new.state, "draft")
        self.assertEqual(doc.current_revision_id, old)
        self.assertEqual(old.state, "published")
        with self.assertRaises(ValidationError):
            wizard.action_create_draft()

    def test_review_counts_and_pagination(self):
        doc = self.documents["general"]
        self.assertIn(doc.id, {row["id"] for row in self.center(self.manager, filter_key="due")["documents"]})
        doc.current_revision_id.write({"review_date": fields.Date.subtract(fields.Date.today(), days=1)})
        self.assertIn(doc.id, {row["id"] for row in self.center(self.manager, filter_key="overdue")["documents"]})
        self.assertEqual(self.center(self.reader, offset=1000)["documents"], [])
        compact = self.center(self.reader, include_summary=False)
        self.assertNotIn("counts", compact)
        self.assertNotIn("needs_attention", compact)

    def test_original_routes_and_direct_urls_for_all_roles(self):
        for user, allowed in [(self.reader, {"general"}), (self.confidential, {"general", "confidential"}),
                              (self.manager, {"general", "restricted", "confidential"})]:
            self.authenticate(user.login, user.login)
            for level, doc in self.documents.items():
                for route in ["preview", "download"]:
                    response = self.url_open("/buz_document/%s/%s" % (route, doc.current_revision_id.id))
                    self.assertEqual(response.status_code, 200 if level in allowed else 403)
        self.authenticate(self.reader.login, self.reader.login)
        self.assertEqual(self.url_open("/buz_document/preview/2147483647").status_code, 404)

    def test_restricted_group_membership_grants_access(self):
        self.reader.write({"groups_id": [fields.Command.link(self.department_group.id)]})
        data = self.center(self.reader, query="BDC-restricted")
        self.assertEqual([row["id"] for row in data["documents"]], [self.documents["restricted"].id])

    def test_restricted_revision_cannot_be_read_directly(self):
        revision = self.documents["restricted"].current_revision_id
        with self.assertRaises(AccessError):
            revision.with_user(self.reader).read(["original_filename"])
        self.assertFalse(self.env["buz.document.revision"].with_user(self.reader).search([("id", "=", revision.id)]))

    def test_download_filename_preserves_revision_and_thai_text(self):
        from ..controllers.document_controller import BuzDocumentController
        self.assertEqual(BuzDocumentController._filename("QP-ITD-01_Rev04.pdf", "file"), "QP-ITD-01_Rev04.pdf")
        self.assertEqual(BuzDocumentController._filename("แบบฟอร์ม.docx", "file"), "แบบฟอร์ม.docx")
        self.assertNotIn("\n", BuzDocumentController._filename("test\nheader.pdf", "file"))

    def test_role_views_hide_mutation_controls(self):
        view = self.env.ref("buz_document_control.view_buz_document_form")
        from lxml import etree
        for user in (self.reader, self.confidential):
            arch = self.env["buz.document"].with_user(user).get_view(view.id, "form")["arch"]
            root = etree.fromstring(arch.encode())
            self.assertFalse(root.xpath("//button[@name='action_new_revision' or @name='action_archive']"))
            self.assertFalse(root.xpath("//field[@name='message_ids' or @name='message_follower_ids']"))
