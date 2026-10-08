"""Run inside Odoo 17 on a disposable database; no live Lazada calls.

Paths that commit the cursor (pack / ready to ship) are covered offline in
qa/test_shipping_offline.py; Odoo tests may not commit.
"""
import base64
import io
import zipfile
from unittest.mock import Mock

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..models.lazada_api import LazadaAPIError
from ..models.lazada_fulfillment import definitive
from ..models.lazada_shipping_helpers import ShippingRejected, ShippingValidationError


def _awb(content=None, url=None):
    data = {'doc_type': 'PDF'}
    if content:
        data['file'] = base64.b64encode(content).decode()
    if url:
        data['pdf_url'] = url
    return {'result': {'success': True, 'data': data}, 'code': '0'}


@tagged('post_install', '-at_install')
class TestLazadaFulfillment(TransactionCase):
    def setUp(self):
        super().setUp()
        self.config = self.env['lazada.config'].create({
            'name': 'Shipping Test Seller', 'app_key': '100', 'app_secret': 'test-only',
            'region': 'th', 'seller_id': '200', 'access_token': 'test-only',
            'token_expires_at': '2999-01-01 00:00:00',
        })
        self.partner = self.env['res.partner'].with_context(skip_partner_required_fields=True).create({
            'name': 'Shipping Test Customer',
        })
        self.order = self.env['sale.order'].create({
            'partner_id': self.partner.id, 'is_lazada_order': True,
            'lazada_config_id': self.config.id, 'lazada_order_id': '9001',
        })
        self.job = self.env['lazada.fulfillment.job'].create({'order_id': self.order.id})

    def _client(self, *statuses, **extra):
        client = Mock()
        client.get_order_items.return_value = [
            dict({'order_item_id': 100 + index, 'status': status}, **extra)
            for index, status in enumerate(statuses)
        ]
        return client

    def test_prepare_waits_for_explicit_queue(self):
        client = self._client('pending', 'pending')
        self.job._prepare(client, 'token')
        self.assertEqual(self.job.state, 'choice')
        self.assertEqual(self.order.lazada_order_status, 'pending')
        self.job.action_queue()
        self.assertEqual(self.job.state, 'queued')
        client.pack_order.assert_not_called()

    def test_uncertain_pack_not_resent(self):
        self.job.shipment_requested_at = '2026-09-17 00:00:00'
        client = self._client('pending')
        self.job._prepare(client, 'token')
        self.assertEqual(self.job.state, 'uncertain')
        client.pack_order.assert_not_called()

    def test_packed_order_needs_queue_before_ready_to_ship(self):
        client = self._client('packed', package_id='FP1', tracking_code='LEX1')
        self.job._prepare(client, 'token')
        self.assertEqual(self.job.state, 'choice')
        self.assertEqual(self.job.package_number, 'FP1')
        self.assertEqual(self.job.tracking_number, 'LEX1')
        client.ready_to_ship.assert_not_called()

    def test_arranged_order_goes_to_label_without_repack(self):
        client = self._client('ready_to_ship', package_id='FP1', tracking_code='LEX1')
        self.job._prepare(client, 'token')
        self.assertEqual(self.job.state, 'shipped')
        self.assertTrue(self.job.arranged_at)
        client.pack_order.assert_not_called()
        client.ready_to_ship.assert_not_called()

    def test_cancelled_items_are_ignored_and_all_cancelled_rejected(self):
        client = self._client('canceled', 'pending')
        self.job._prepare(client, 'token')
        self.assertEqual(self.job.state, 'choice')
        with self.assertRaises(ShippingValidationError):
            self.job._prepare(self._client('canceled', 'canceled'), 'token')

    def test_unmapped_line_blocks_pack(self):
        self.job.state = 'queued'
        client = self._client('pending')
        with self.assertRaises(UserError):
            self.job._ship(client, 'token')
        client.pack_order.assert_not_called()
        self.assertFalse(self.job.shipment_requested_at)

    def test_label_from_inline_pdf(self):
        self.job.write({'state': 'shipped', 'arranged_at': fields.Datetime.now()})
        client = self._client('ready_to_ship', package_id='FP1', tracking_code='LEX1')
        client.get_awb_document.return_value = _awb(content=b'%PDF-fixture')
        self.job._create_label(client, 'token')
        self.assertEqual(self.job.state, 'ready')
        self.assertEqual(base64.b64decode(self.job.label_data), b'%PDF-fixture')
        client.get_awb_document.assert_called_once_with('token', ['FP1'])
        client.download_document.assert_not_called()

    def test_label_downloaded_from_url(self):
        self.job.write({'state': 'shipped', 'arranged_at': fields.Datetime.now()})
        client = self._client('ready_to_ship', package_id='FP1', tracking_code='LEX1')
        client.get_awb_document.return_value = _awb(url='https://example.com/awb.pdf')
        client.download_document.return_value = b'%PDF-from-url'
        self.job._create_label(client, 'token')
        self.assertEqual(self.job.state, 'ready')
        client.download_document.assert_called_once_with('https://example.com/awb.pdf')

    def test_definitive_errors(self):
        self.assertTrue(definitive(LazadaAPIError('IllegalAccessToken', 'x', error_type='ISV')))
        self.assertTrue(definitive(ShippingRejected('item status is not pending')))
        self.assertFalse(definitive(LazadaAPIError('network', 'timeout')))
        self.assertFalse(definitive(LazadaAPIError('http_502', '')))
        self.assertFalse(definitive(LazadaAPIError('ServiceTimeout', '', error_type='ISP')))
        self.assertFalse(definitive(ShippingValidationError('Missing Lazada result object.')))

    def test_repeat_batch_reuses_job(self):
        first = self.order.action_lazada_shipping_batch()
        second = self.order.action_lazada_shipping_batch()
        batches = self.env['lazada.fulfillment.batch'].browse([first['res_id'], second['res_id']])
        self.assertEqual(batches[0].job_ids, self.job)
        self.assertEqual(batches[1].job_ids, self.job)

    def test_zip_contains_label_and_manifest(self):
        self.job.write({'state': 'ready', 'label_filename': 'test-label.pdf',
                        'label_data': base64.b64encode(b'%PDF-fixture')})
        batch = self.env['lazada.fulfillment.batch'].create({'job_ids': [fields.Command.set(self.job.ids)]})
        batch.action_download()
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(batch.file_data))) as archive:
            self.assertEqual(set(archive.namelist()), {'test-label.pdf', 'results.csv'})
            self.assertIn(self.order.lazada_order_id.encode(), archive.read('results.csv'))

    def test_partial_batch_lists_failed_order_without_fake_label(self):
        other_order = self.order.copy({'lazada_order_id': '9002',
                                       'is_lazada_order': True, 'lazada_config_id': self.config.id})
        failed = self.env['lazada.fulfillment.job'].create({'order_id': other_order.id, 'state': 'error', 'message': 'Label not ready'})
        self.job.write({'state': 'ready', 'label_filename': 'qa-label.pdf',
                        'label_data': base64.b64encode(b'%PDF-fixture')})
        batch = self.env['lazada.fulfillment.batch'].create({
            'job_ids': [fields.Command.set((self.job | failed).ids)],
        })
        batch.action_download()
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(batch.file_data))) as archive:
            self.assertEqual(set(archive.namelist()), {'qa-label.pdf', 'results.csv'})
            self.assertIn(b'9002', archive.read('results.csv'))
            self.assertIn(b'Label not ready', archive.read('results.csv'))
        self.assertIn('1 of 2', batch.download_note)
