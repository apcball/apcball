import base64

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestDocumentControl(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = cls.env.ref("base.group_user").id
        cls.manager = cls.env["res.users"].create({"name": "Manager", "login": "doc_manager", "groups_id": [fields.Command.set([internal, cls.env.ref("buz_document_control.group_document_manager").id])]})
        cls.user = cls.env["res.users"].create({"name": "User", "login": "doc_user", "groups_id": [fields.Command.set([internal, cls.env.ref("buz_document_control.group_document_user").id])]})
        cls.conf_user = cls.env["res.users"].create({"name": "Confidential", "login": "doc_conf", "groups_id": [fields.Command.set([internal, cls.env.ref("buz_document_control.group_document_confidential_user").id])]})

    def _document(self, security="general"):
        return self.env["buz.document"].with_user(self.manager).create({"name": "Test", "document_no": "TEST-%s" % security, "security_level": security})

    def _revision(self, document, revision="01"):
        return self.env["buz.document.revision"].with_user(self.manager).create({"document_id": document.id, "revision": revision, "effective_date": "2026-01-01", "change_description": "Initial issue", "original_file": base64.b64encode(b"%PDF-1.4"), "original_filename": "test.pdf"})

    def test_publish_replaces_old_current_revision(self):
        doc = self._document()
        first = self._revision(doc, "01"); first.action_publish()
        second = self._revision(doc, "02"); second.action_publish()
        self.assertEqual(first.state, "obsolete")
        self.assertEqual(second.state, "published")
        self.assertEqual(doc.current_revision_id, second)

    def test_published_file_is_immutable_and_duplicate_is_blocked(self):
        doc = self._document()
        revision = self._revision(doc); revision.action_publish()
        with self.assertRaises(ValidationError):
            revision.write({"original_file": base64.b64encode(b"different")})
        with self.assertRaises(Exception):
            self._revision(doc, "01")

    def test_users_cannot_create_revision(self):
        doc = self._document()
        with self.assertRaises(AccessError):
            self.env["buz.document.revision"].with_user(self.user).create({"document_id": doc.id, "revision": "01", "change_description": "x"})

    def test_confidential_access_requires_confidential_group(self):
        doc = self._document("confidential")
        revision = self._revision(doc)
        revision.action_publish()
        self.assertEqual(self.env["buz.document"].with_user(self.user).search_count([( "id", "=", doc.id)]), 0)
        self.assertEqual(self.env["buz.document"].with_user(self.conf_user).search_count([( "id", "=", doc.id)]), 1)
