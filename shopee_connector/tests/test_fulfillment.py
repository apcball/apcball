"""Run inside Odoo 17 on a disposable database; no live Shopee calls."""
import base64
import io
import zipfile
from unittest.mock import Mock, patch

from odoo.exceptions import UserError
from odoo import fields
from odoo.tests import TransactionCase, tagged

from ..models.shopee_api import ShopeeAPI


@tagged('post_install', '-at_install')
class TestShopeeFulfillment(TransactionCase):
    def setUp(self):
        super().setUp()
        self.config = self.env['shopee.config'].create({
            'name': 'Shipping Test Shop', 'partner_id': '100', 'partner_key': 'test-only',
            'shop_id': '200', 'access_token': 'test-only', 'token_expires_at': '2999-01-01 00:00:00',
        })
        self.partner = self.env['res.partner'].with_context(skip_partner_required_fields=True).create({
            'name': 'Shipping Test Customer',
        })
        self.order = self.env['sale.order'].create({
            'partner_id': self.partner.id, 'is_shopee_order': True,
            'shopee_config_id': self.config.id, 'shopee_order_sn': 'TEST-FULFILLMENT-1',
        })
        self.job = self.env['shopee.fulfillment.job'].create({'order_id': self.order.id})

    def test_prepare_requires_explicit_option(self):
        client = Mock()
        client.get_order_detail.return_value = {'response': {'order_list': [{
            'order_sn': self.order.shopee_order_sn, 'order_status': 'READY_TO_SHIP',
        }]}}
        client.get_shipping_parameter.return_value = {'response': {'info_needed': {'dropoff': []}}}
        self.job._prepare(client, 'token')
        self.assertEqual(self.job.state, 'choice')
        self.assertFalse(self.job.option_id)
        with self.assertRaises(UserError):
            self.job.action_queue()
        self.job.option_id = self.job.option_ids[0]
        self.job.action_queue()
        self.assertEqual(self.job.state, 'queued')
        client.ship_order.assert_not_called()

    def test_uncertain_shipment_not_resent(self):
        self.job.shipment_requested_at = '2026-09-17 00:00:00'
        client = Mock()
        client.get_order_detail.return_value = {'response': {'order_list': [{
            'order_sn': self.order.shopee_order_sn, 'order_status': 'READY_TO_SHIP',
        }]}}
        self.job._prepare(client, 'token')
        self.assertEqual(self.job.state, 'uncertain')
        client.ship_order.assert_not_called()
        client.get_shipping_parameter.assert_not_called()

    def test_arranged_order_goes_to_label_without_reship(self):
        client = Mock()
        client.get_order_detail.return_value = {'response': {'order_list': [{
            'order_sn': self.order.shopee_order_sn, 'order_status': 'PROCESSED',
        }]}}
        self.job._prepare(client, 'token')
        self.assertEqual(self.job.state, 'shipped')
        client.ship_order.assert_not_called()

    def test_cancelled_order_rejected(self):
        client = Mock()
        client.get_order_detail.return_value = {'response': {'order_list': [{
            'order_sn': self.order.shopee_order_sn, 'order_status': 'CANCELLED',
        }]}}
        with self.assertRaises(UserError):
            self.job._prepare(client, 'token')
        client.ship_order.assert_not_called()

    def test_repeat_batch_reuses_job(self):
        first = self.order.action_shopee_shipping_batch()
        second = self.order.action_shopee_shipping_batch()
        batches = self.env['shopee.fulfillment.batch'].browse([first['res_id'], second['res_id']])
        self.assertEqual(batches[0].job_ids, self.job)
        self.assertEqual(batches[1].job_ids, self.job)

    def test_poll_processing_does_not_download(self):
        self.job.state = 'document'
        client = Mock()
        client.get_shipping_document_result.return_value = {'response': {'result_list': [{
            'order_sn': self.order.shopee_order_sn, 'status': 'PROCESSING',
        }]}}
        self.job._poll_label(client, 'token')
        self.assertEqual(self.job.state, 'document')
        client.download_shipping_document.assert_not_called()

    def test_zip_contains_label_and_manifest(self):
        self.job.write({'state': 'ready', 'label_filename': 'test-label.pdf',
                        'label_data': base64.b64encode(b'%PDF-fixture')})
        batch = self.env['shopee.fulfillment.batch'].create({'job_ids': [fields.Command.set(self.job.ids)]})
        batch.action_download()
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(batch.file_data))) as archive:
            self.assertEqual(set(archive.namelist()), {'test-label.pdf', 'results.csv'})
            self.assertIn(self.order.shopee_order_sn.encode(), archive.read('results.csv'))

    def test_partial_batch_lists_failed_order_without_fake_label(self):
        other_order = self.order.copy({'shopee_order_sn': 'QA-FAILED-LABEL',
                                       'is_shopee_order': True, 'shopee_config_id': self.config.id})
        failed = self.env['shopee.fulfillment.job'].create({'order_id': other_order.id, 'state': 'error', 'message': 'Label not ready'})
        self.job.write({'state': 'ready', 'label_filename': 'qa-label.pdf',
                        'label_data': base64.b64encode(b'%PDF-fixture')})
        batch = self.env['shopee.fulfillment.batch'].create({
            'job_ids': [fields.Command.set((self.job | failed).ids)],
        })
        batch.action_download()
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(batch.file_data))) as archive:
            self.assertEqual(set(archive.namelist()), {'qa-label.pdf', 'results.csv'})
            self.assertIn(b'QA-FAILED-LABEL', archive.read('results.csv'))
            self.assertIn(b'Label not ready', archive.read('results.csv'))
        self.assertIn('1 of 2', batch.download_note)
