"""Offline checks: actual API adapter + pure validation, no Odoo/database needed."""
import base64
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'models' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

api = load('lazada_api')
h = load('lazada_shipping_helpers')


def ok(data):
    return {'result': {'success': True, 'data': data}, 'code': '0'}


class TestShippingAdapter(unittest.TestCase):
    def setUp(self):
        self.client = api.LazadaAPI('100', 'not-a-real-secret', 'th')

    def test_pack_payload(self):
        with patch.object(self.client, '_request', return_value={}) as call:
            self.client.pack_order('token', '9001', ['101', 102])
        self.assertEqual(call.call_args.args[:2], ('POST', '/order/fulfill/pack'))
        self.assertEqual(json.loads(call.call_args.kwargs['params']['packReq']), {
            'pack_order_list': [{'order_id': 9001, 'order_item_list': [101, 102]}],
            'delivery_type': 'dropship', 'shipping_allocate_type': 'TFS',
        })
        self.assertEqual(call.call_args.kwargs['retries'], 1)
        self.assertTrue(call.call_args.kwargs['raw'])

    def test_rts_and_document_payloads(self):
        with patch.object(self.client, '_request', return_value={}) as call:
            self.client.ready_to_ship('token', ['FP1', 'FP2'])
        self.assertEqual(call.call_args.args[1], '/order/package/rts')
        self.assertEqual(json.loads(call.call_args.kwargs['params']['readyToShipReq']),
                         {'packages': [{'package_id': 'FP1'}, {'package_id': 'FP2'}]})
        self.assertEqual(call.call_args.kwargs['retries'], 1)
        with patch.object(self.client, '_request', return_value={}) as call:
            self.client.get_awb_document('token', ['FP1'])
        self.assertEqual(call.call_args.args[1], '/order/package/document/get')
        self.assertEqual(json.loads(call.call_args.kwargs['params']['getDocumentReq']),
                         {'doc_type': 'PDF', 'packages': [{'package_id': 'FP1'}]})

    def test_timeout_never_replays_pack(self):
        with patch.object(api.requests, 'request', side_effect=api.requests.Timeout('timeout')) as call:
            with self.assertRaises(api.LazadaAPIError) as caught:
                self.client.pack_order('token', '9001', ['101'])
        self.assertEqual(call.call_count, 1)
        self.assertEqual(caught.exception.error, 'network')

    def test_server_error_never_replays_ready_to_ship(self):
        with patch.object(api.requests, 'request', return_value=Mock(status_code=503)) as call:
            with self.assertRaises(api.LazadaAPIError):
                self.client.ready_to_ship('token', ['FP1'])
        self.assertEqual(call.call_count, 1)

    def test_read_calls_are_retried(self):
        with patch.object(api.time, 'sleep'), \
             patch.object(api.requests, 'request', side_effect=api.requests.Timeout('timeout')) as call:
            with self.assertRaises(api.LazadaAPIError):
                self.client.get_order_items('token', '9001')
        self.assertEqual(call.call_count, 3)

    def test_post_params_go_in_body_and_raw_response_is_returned(self):
        reply = Mock(status_code=200)
        reply.json.return_value = ok({'pack_order_list': []})
        with patch.object(api.requests, 'request', return_value=reply) as call:
            data = self.client.pack_order('secret-token', '9001', ['101'])
        self.assertEqual(data, reply.json.return_value)
        self.assertIn('packReq', call.call_args.kwargs['data'])
        self.assertNotIn('packReq', call.call_args.kwargs['params'])
        self.assertEqual(call.call_args.kwargs['params']['access_token'], 'secret-token')

    def test_business_error_keeps_lazada_type(self):
        reply = Mock(status_code=200)
        reply.json.return_value = {'code': 'ServiceTimeout', 'type': 'ISP', 'message': 'busy'}
        with patch.object(api.requests, 'request', return_value=reply):
            with self.assertRaises(api.LazadaAPIError) as caught:
                self.client.pack_order('token', '9001', ['101'])
        self.assertEqual(caught.exception.error_type, 'ISP')

    def test_logs_mask_token(self):
        logs = []
        self.client.log_callback = lambda **values: logs.append(values)
        reply = Mock(status_code=200)
        reply.json.return_value = ok({'packages': []})
        with patch.object(api.requests, 'request', return_value=reply):
            self.client.ready_to_ship('secret-token', ['FP1'])
        self.assertEqual(logs[0]['request_data']['params']['access_token'], '***')
        self.assertIn('readyToShipReq', logs[0]['request_data']['body'])

    def test_download_requires_https_pdf(self):
        with self.assertRaises(api.LazadaAPIError):
            self.client.download_document('http://example.com/awb.pdf')
        reply = Mock(status_code=200, content=b'<html>expired</html>')
        with patch.object(api.requests, 'get', return_value=reply):
            with self.assertRaises(api.LazadaAPIError):
                self.client.download_document('https://example.com/awb.pdf')

    def test_download_logs_without_signature(self):
        logs = []
        self.client.log_callback = lambda **values: logs.append(values)
        reply = Mock(status_code=200, content=b'%PDF-1.4 data')
        with patch.object(api.requests, 'get', return_value=reply):
            content = self.client.download_document('https://example.com/awb.pdf?Signature=secret')
        self.assertTrue(content.startswith(b'%PDF-'))
        self.assertEqual(logs[0]['endpoint'], 'https://example.com/awb.pdf')
        self.assertEqual(logs[0]['response_data']['format'], 'pdf')


class TestStockPricePayload(unittest.TestCase):
    def setUp(self):
        self.client = api.LazadaAPI('100', 'not-a-real-secret', 'th')

    def _skus(self, call):
        payload = call.call_args.kwargs['params']['payload']
        return ElementTree.fromstring(payload).findall('./Product/Skus/Sku')

    def test_stock_batch_has_one_sku_per_variant_and_no_price(self):
        with patch.object(self.client, '_post', return_value={}) as call:
            self.client.update_stock_batch('token', [
                {'seller_sku': 'A&1', 'sku_id': '11', 'item_id': '7', 'quantity': 3.0},
                {'seller_sku': 'B', 'sku_id': '12', 'item_id': '7', 'quantity': -2},
            ])
        skus = self._skus(call)
        self.assertEqual([s.findtext('SellerSku') for s in skus], ['A&1', 'B'])
        self.assertEqual([s.findtext('Quantity') for s in skus], ['3', '0'])
        self.assertTrue(all(s.find('Price') is None for s in skus))

    def test_price_payload_has_price_and_no_quantity(self):
        with patch.object(self.client, '_post', return_value={}) as call:
            self.client.update_price('token', [{'seller_sku': 'A', 'sku_id': '11', 'item_id': '7', 'price': 100}])
        sku = self._skus(call)[0]
        self.assertEqual(sku.findtext('Price'), '100.00')
        self.assertIsNone(sku.find('Quantity'))
        self.assertEqual(call.call_args.args[0], '/product/price_quantity/update')

    def test_network_error_message_hides_signed_url(self):
        with patch.object(api.time, 'sleep'), patch.object(
                api.requests, 'request',
                side_effect=api.requests.ConnectionError('https://x/?access_token=secret&sign=abc')):
            with self.assertRaises(api.LazadaAPIError) as caught:
                self.client.get_order_items('secret', '9001')
        self.assertNotIn('secret', str(caught.exception))

    def test_finance_transactions_request_and_list(self):
        rows = [{'fee_name': 'Commission', 'amount': '-5.00'}]
        with patch.object(self.client, '_request', return_value=rows) as call:
            result = self.client.get_finance_transactions('token', 9001, '2026-09-20', '2026-09-30')
        self.assertEqual(result, rows)
        self.assertEqual(call.call_args.args[:2], ('GET', '/finance/transaction/details/get'))
        params = call.call_args.kwargs['params']
        self.assertEqual((params['trade_order_id'], params['start_time'], params['end_time']),
                         ('9001', '2026-09-20', '2026-09-30'))
        with patch.object(self.client, '_request', return_value={}):
            self.assertEqual(self.client.get_finance_transactions('token', 1, 'a', 'b'), [])

    def test_mask_is_case_insensitive_and_nested(self):
        masked = api._mask_value({'Authorization': 'x', 'nested': [{'ACCESS_TOKEN': 'y'}]})
        self.assertEqual(masked, {'Authorization': '***', 'nested': [{'ACCESS_TOKEN': '***'}]})


class TestShippingValidation(unittest.TestCase):
    def test_stages(self):
        self.assertEqual(h.classify_items([{'status': 'pending'}, {'status': 'canceled'}])[0], 'pending')
        self.assertEqual(h.classify_items([{'status': 'packed'}])[0], 'packed')
        self.assertEqual(h.classify_items([{'status': 'ready_to_ship'}, {'status': 'shipped'}])[0], 'arranged')

    def test_unsupported_orders_not_guessed(self):
        for items in (
            [], [{'status': 'canceled'}], [{'status': 'unpaid'}],
            [{'status': 'pending'}, {'status': 'packed'}],
            [{'status': 'returned'}],
            [{'status': 'pending', 'is_digital': 1}],
            [{'status': 'pending', 'delivery_option_sof': '1'}],
        ):
            with self.assertRaises(h.ShippingValidationError, msg=items):
                h.classify_items(items)

    def test_packages_unique(self):
        items = [{'package_id': 'FP1', 'tracking_code': 'T1'}, {'package_id': 'FP1', 'tracking_code': 'T1'},
                 {'package_id': 'FP2', 'tracking_code': 'T2'}]
        self.assertEqual(h.packages(items), (['FP1', 'FP2'], ['T1', 'T2']))

    def test_pack_result(self):
        data = ok({'pack_order_list': [{'order_id': 9001, 'order_item_list': [
            {'order_item_id': 101, 'item_err_code': '0', 'msg': 'success', 'package_id': 'FP1',
             'tracking_number': 'LEX1', 'shipment_provider': 'LEX TH'},
        ]}]})
        self.assertEqual(h.pack_result(data, '9001'), (['FP1'], ['LEX1'], ['LEX TH']))

    def test_pack_item_error_is_rejection(self):
        data = ok({'pack_order_list': [{'order_id': 9001, 'order_item_list': [
            {'order_item_id': 101, 'item_err_code': '82', 'msg': 'Item status is not pending'},
        ]}]})
        with self.assertRaises(h.ShippingRejected):
            h.pack_result(data, '9001')

    def test_pack_missing_result_is_not_rejection(self):
        for data in (ok({'pack_order_list': []}), {'code': '0'}):
            with self.assertRaises(h.ShippingValidationError) as caught:
                h.pack_result(data, '9001')
            self.assertNotIsInstance(caught.exception, h.ShippingRejected)

    def test_unsuccessful_result_is_rejection(self):
        with self.assertRaises(h.ShippingRejected):
            h.result({'result': {'success': False, 'error_msg': 'Invalid package'}})

    def test_rts_result(self):
        h.rts_result(ok({'packages': [{'package_id': 'FP1', 'item_err_code': '0'}]}), ['FP1'])
        with self.assertRaises(h.ShippingRejected):
            h.rts_result(ok({'packages': [{'package_id': 'FP1', 'item_err_code': '1', 'msg': 'bad'}]}), ['FP1'])
        # A missing row is not proof that Lazada ignored the package.
        with self.assertRaises(h.ShippingValidationError) as caught:
            h.rts_result(ok({'packages': []}), ['FP1'])
        self.assertNotIsInstance(caught.exception, h.ShippingRejected)

    def test_document(self):
        pdf = base64.b64encode(b'%PDF-1.4').decode()
        self.assertEqual(h.document(ok({'doc_type': 'PDF', 'file': pdf})), (b'%PDF-1.4', None))
        self.assertEqual(h.document(ok({'pdf_url': 'https://x/awb.pdf', 'file': 'bm90IGEgcGRm'})),
                         (None, 'https://x/awb.pdf'))
        for data in (ok({}), ok({'doc_type': 'HTML', 'file': pdf})):
            with self.assertRaises(h.ShippingValidationError):
                h.document(data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
