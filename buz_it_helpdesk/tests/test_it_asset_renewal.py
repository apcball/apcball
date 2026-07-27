from datetime import date, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestItAssetRenewal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.manager_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_manager")
        cls.agent_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_agent")
        cls.manager = cls.env["res.users"].sudo().create({
            "name": "Renewal Manager", "login": "renewal.manager.5d",
            "email": "renewal.manager@example.com",
            "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, cls.manager_group.id])],
        })
        cls.agent = cls.env["res.users"].sudo().create({
            "name": "Renewal Agent", "login": "renewal.agent.5d",
            "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, cls.agent_group.id])],
        })

    def _asset(self, expiry=None):
        return self.env["buz.it.asset"].with_user(self.manager).create({
            "asset_type": "software_license", "asset_name": "5D License",
            "license_product": "Renewable Suite", "license_version": "2026",
            "license_start_date": date(2026, 1, 1),
            "license_expiry_date": expiry or date(2026, 12, 31), "license_seats": 5,
        })

    def test_phase_5d_renewed_requires_evidence_updates_asset_and_starts_next_cycle(self):
        asset = self._asset()
        renewal = self.env["buz.it.asset.renewal"].with_user(self.manager).create({"asset_id": asset.id})
        self.assertEqual(len(renewal.notification_ids), 4)
        renewal.action_start()
        with self.assertRaises(ValidationError):
            renewal.action_mark_renewed()
        evidence = self.env["ir.attachment"].sudo().create({
            "name": "license-certificate.pdf", "datas": "dGVzdA==",
            "res_model": renewal._name, "res_id": renewal.id,
        })
        renewal.write({"new_expiry_date": date(2027, 12, 31), "evidence_attachment_ids": [fields.Command.link(evidence.id)]})
        next_renewal = renewal.action_mark_renewed()
        self.assertEqual(renewal.status, "renewed")
        self.assertEqual(asset.license_expiry_date, date(2027, 12, 31))
        self.assertEqual(next_renewal.previous_renewal_id, renewal)
        self.assertEqual(next_renewal.status, "pending_review")
        self.assertTrue(next_renewal.notification_ids)
        self.assertIn("renewal_renewed", asset.history_ids.sudo().mapped("event_type"))

    def test_phase_5d_notification_dedupe_catchup_and_secret_safe_payload(self):
        asset = self._asset(expiry=date.today() - timedelta(days=1))
        config = self.env["buz.it.asset.notification.config"].with_user(self.manager).create({
            "company_id": self.company.id, "timezone": "Asia/Bangkok",
            "recipient_ids": [fields.Command.set([self.manager.id])],
        })
        renewal = self.env["buz.it.asset.renewal"].with_user(self.manager).create({
            "asset_id": asset.id, "new_expiry_date": date.today() - timedelta(days=1),
        })
        log = renewal.notification_ids.filtered(lambda item: item.notification_type == "expired")
        self.assertEqual(len(log), 1)
        self.assertEqual(renewal.notification_ids.search_count([("dedupe_key", "=", log.dedupe_key)]), 1)
        self.assertNotIn("license_key", (log._safe_subject_body()[0] + log._safe_subject_body()[1]).lower())
        with patch.object(type(log), "_recipient_users", return_value=self.manager), patch.object(
            type(self.env["mail.mail"]), "send", return_value=True
        ):
            log._send()
        self.assertEqual(log.state, "sent")
        self.assertTrue(log.sent_at)
        self.assertTrue(renewal.activity_ids)
        self.assertTrue(renewal.message_ids)
        self.assertEqual(config.timezone, "Asia/Bangkok")

    def test_phase_5d_failed_notification_is_retryable_and_auditable(self):
        renewal = self.env["buz.it.asset.renewal"].with_user(self.manager).create({"asset_id": self._asset().id})
        log = renewal.notification_ids[0]
        with patch.object(type(log), "_recipient_users", return_value=self.manager), patch.object(
            type(self.env["mail.mail"]), "send", side_effect=RuntimeError("SMTP unavailable")
        ):
            self.assertFalse(log._send())
        self.assertEqual(log.state, "failed")
        self.assertEqual(log.retry_count, 1)
        self.assertIn("SMTP unavailable", log.error_detail)
        with self.assertRaises(UserError):
            renewal.unlink()
        with self.assertRaises(AccessError):
            self.env["buz.it.asset.notification.log"].with_user(self.agent).search([]).write({"state": "sent"})
    def test_phase_5d_expired_cancel_and_direct_status_transition_are_controlled(self):
        asset = self._asset()
        expired = self.env["buz.it.asset.renewal"].with_user(self.manager).create({"asset_id": asset.id})
        expired.action_mark_expired()
        self.assertEqual(expired.status, "expired")
        self.assertIn("renewal_expired", asset.history_ids.sudo().mapped("event_type"))

        cancelled = self.env["buz.it.asset.renewal"].with_user(self.manager).create({"asset_id": asset.id})
        with self.assertRaises(UserError):
            cancelled.write({"status": "cancelled"})
        cancelled.action_cancel()
        self.assertEqual(cancelled.status, "cancelled")
        self.assertIn("renewal_cancelled", asset.history_ids.sudo().mapped("event_type"))
