"""Pure validation used by the fulfillment worker and offline tests."""
import base64
import binascii

PACKABLE = {'pending'}
PACKED = {'packed', 'repacked'}
ARRANGED = {'ready_to_ship', 'ready_to_ship_pending', 'shipped', 'delivered'}
CANCELLED = {'canceled', 'cancelled'}


class ShippingValidationError(ValueError):
    pass


class ShippingRejected(ShippingValidationError):
    """Lazada explicitly rejected the request; nothing to reconcile."""


def result(data):
    """Return ``result.data`` of a fulfillment (pack/RTS/AWB) response."""
    if not isinstance(data, dict):
        raise ShippingValidationError('Invalid Lazada response.')
    value = data.get('result')
    if not isinstance(value, dict):
        raise ShippingValidationError('Missing Lazada result object.')
    if str(value.get('success')).lower() != 'true':
        raise ShippingRejected(str(value.get('error_msg') or value.get('error_code')
                                   or 'Lazada rejected the request.'))
    payload = value.get('data')
    if not isinstance(payload, dict):
        raise ShippingValidationError('Missing Lazada result data.')
    return payload


def _failed(row):
    return str(row.get('item_err_code')) != '0'


def _reason(row):
    return str(row.get('msg') or row.get('item_err_code') or row)


def classify_items(items):
    """Return (stage, active_items) for one order's items.

    Lazada creates one item per unit. Cancelled items are ignored. ``stage``
    is 'pending' (needs pack), 'packed' (needs ready to ship) or 'arranged'
    (ready to ship or later). Unpaid, digital, delivered-by-seller and mixed
    orders are not guessed at.
    """
    if not isinstance(items, list) or not items:
        raise ShippingValidationError('Lazada returned no order items.')
    active = [i for i in items if str(i.get('status') or '').lower() not in CANCELLED]
    if not active:
        raise ShippingValidationError('Every item of this Lazada order is cancelled.')
    statuses = {str(i.get('status') or '').lower() for i in active}
    if 'unpaid' in statuses:
        raise ShippingValidationError('The Lazada order is unpaid.')
    if any(str(i.get('is_digital')) == '1' for i in active):
        raise ShippingValidationError('Digital orders are not supported; handle them in Seller Center.')
    if any(str(i.get('delivery_option_sof')) == '1' for i in active):
        raise ShippingValidationError('Delivered-by-seller (DBS) orders are not supported; handle them in Seller Center.')
    for stage, allowed in (('pending', PACKABLE), ('packed', PACKED), ('arranged', ARRANGED)):
        if statuses <= allowed:
            return stage, active
    raise ShippingValidationError(
        f'Unsupported or mixed item statuses ({", ".join(sorted(statuses))}). '
        'Handle this order in Seller Center.')


def packages(items):
    """Return (package_ids, tracking_numbers) of items, unique and in order."""
    package_ids, tracking = [], []
    for item in items:
        package_id = str(item.get('package_id') or '')
        number = str(item.get('tracking_code') or item.get('tracking_number') or '')
        if package_id and package_id not in package_ids:
            package_ids.append(package_id)
        if number and number not in tracking:
            tracking.append(number)
    return package_ids, tracking


def pack_result(data, order_id):
    """Return (package_ids, tracking_numbers, providers) of a pack call."""
    rows = [r for r in result(data).get('pack_order_list') or []
            if str(r.get('order_id')) == str(order_id)]
    if len(rows) != 1:
        raise ShippingValidationError('Lazada returned no unique pack result for this order.')
    items = rows[0].get('order_item_list') or []
    if not items:
        raise ShippingValidationError('Lazada returned no packed items for this order.')
    failed = [row for row in items if _failed(row)]
    if failed:
        raise ShippingRejected('; '.join(_reason(row) for row in failed))
    package_ids, tracking = packages(items)
    if not package_ids:
        raise ShippingValidationError('Lazada returned no package for this order.')
    providers = []
    for row in items:
        provider = str(row.get('shipment_provider') or '')
        if provider and provider not in providers:
            providers.append(provider)
    return package_ids, tracking, providers


def rts_result(data, package_ids):
    rows = {str(r.get('package_id')): r for r in result(data).get('packages') or []}
    failed = [f'{p}: {_reason(rows[str(p)])}' for p in package_ids
              if str(p) in rows and _failed(rows[str(p)])]
    if failed:
        raise ShippingRejected('; '.join(failed))
    missing = [str(p) for p in package_ids if str(p) not in rows]
    if missing:
        raise ShippingValidationError(f'Lazada returned no ready-to-ship result for {", ".join(missing)}.')


def document(data):
    """Return (pdf_bytes or None, pdf_url or None) of a PrintAWB response."""
    value = result(data)
    if value.get('doc_type') and str(value.get('doc_type')).upper() != 'PDF':
        raise ShippingValidationError('Lazada did not return a PDF label.')
    content = None
    if value.get('file'):
        try:
            decoded = base64.b64decode(value['file'])
        except (binascii.Error, TypeError, ValueError):
            decoded = b''
        content = decoded if decoded.startswith(b'%PDF-') else None
    url = value.get('pdf_url') or None
    if not content and not url:
        raise ShippingValidationError('Lazada returned no AWB document.')
    return content, url
