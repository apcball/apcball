"""Pure parsing of the Lazada Seller Center order export (no Odoo needed).

The export has one row per order item with camelCase headers such as
``orderNumber``, ``shippingAddress``…``shippingAddress5``, ``taxCode`` and
``sellerDiscountTotal``. Rows are turned into dicts shaped like the Open
Platform's ``/order/get`` response so the API code paths can reuse them.
"""
import re
from datetime import datetime

# key -> accepted normalised headers (camelCase export and "Title Case" forms)
COLUMNS = {
    "order_number": ("ordernumber",),
    "status": ("status",),
    "create_time": ("createtime",),
    "tax_code": ("taxcode",),
    "branch_number": ("branchnumber",),
    "tax_requested": ("taxinvoicerequested",),
    "unit_price": ("unitprice",),
    "paid_price": ("paidprice",),
    "seller_discount": ("sellerdiscounttotal",),
    "shipping_fee": ("shippingfee",),
}
for _prefix, _addr in (("shipping", "shippingaddress"), ("billing", "billingaddr")):
    COLUMNS[f"{_prefix}_name"] = (f"{_prefix}name",)
    COLUMNS[f"{_prefix}_address1"] = (_addr, f"{_prefix}address", f"{_prefix}address1")
    for _n in range(2, 6):
        COLUMNS[f"{_prefix}_address{_n}"] = (f"{_addr}{_n}", f"{_prefix}address{_n}")
    for _key in ("phone", "phone2", "city", "postcode", "country"):
        COLUMNS[f"{_prefix}_{_key}"] = (f"{_prefix}{_key}",)

REQUIRED = ("order_number", "shipping_address1")
MONEY = ("unit_price", "paid_price", "seller_discount", "shipping_fee")
TRUE = {"true", "yes", "y", "1", "ใช่"}
CANCELLED = {"canceled", "cancelled"}
_TIME_FORMATS = ("%d %b %Y %H:%M", "%d %b %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


class ExportFormatError(ValueError):
    pass


def normalise_header(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def cell(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def amount(text):
    if text in ("", None):
        return None
    try:
        return float(str(text).replace(",", ""))
    except ValueError:
        return None


def parse_create_time(text):
    """Seller Center times ("07 Oct 2026 21:14") are shop-local; naive result."""
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(str(text).strip(), fmt)
        except (TypeError, ValueError):
            continue
    return None


def column_indexes(headers):
    """Return {key: column index} for the known columns of the export."""
    positions = {}
    for index, header in enumerate(headers):
        positions.setdefault(normalise_header(header), index)
    indexes = {}
    for key, aliases in COLUMNS.items():
        index = next((positions[a] for a in aliases if a in positions), None)
        if index is not None:
            indexes[key] = index
    missing = [COLUMNS[key][0] for key in REQUIRED if key not in indexes]
    if missing:
        found = [str(h).strip() for h in headers if str(h or "").strip()]
        raise ExportFormatError(
            "This is not a Lazada Seller Center order export. Missing column(s): "
            f"{', '.join(missing)}\nThe file has {len(found)} column(s): "
            + ", ".join(found[:15]) + (" …" if len(found) > 15 else "")
        )
    return indexes


def orders_from_rows(headers, rows):
    """{order_number: /order/get-like dict} from the export rows.

    Each dict has ``order_id``, ``order_number``, ``statuses``,
    ``created_at`` (naive shop-local datetime), ``address_shipping``,
    ``address_billing``, ``tax_code`` (only when a tax invoice was
    requested), ``branch_number`` and ``payment`` (False when the export
    has no money columns).
    """
    indexes = column_indexes(headers)

    def get(row, key):
        index = indexes.get(key)
        return cell(row[index]) if index is not None and index < len(row) else ""

    def address(row, prefix):
        return {
            "first_name": get(row, f"{prefix}_name"),
            **{f"address{n}": get(row, f"{prefix}_address{n}") for n in range(1, 6)},
            "phone": get(row, f"{prefix}_phone"),
            "phone2": get(row, f"{prefix}_phone2"),
            "city": get(row, f"{prefix}_city"),
            "post_code": get(row, f"{prefix}_postcode"),
            "country": get(row, f"{prefix}_country"),
        }

    orders = {}
    for row in rows:
        row = list(row)
        number = get(row, "order_number")
        if not number:
            continue
        order = orders.get(number)
        if order is None:
            requested = ("tax_requested" not in indexes
                         or get(row, "tax_requested").lower() in TRUE)
            order = orders[number] = {
                "order_id": number,
                "order_number": number,
                "statuses": [],
                "created_at": parse_create_time(get(row, "create_time")),
                "address_shipping": address(row, "shipping"),
                "address_billing": address(row, "billing"),
                "tax_code": get(row, "tax_code") if requested else "",
                "branch_number": get(row, "branch_number"),
                "_items": [],
            }
        status = get(row, "status").lower()
        order["statuses"].append(status)
        order["_items"].append(dict({key: amount(get(row, key)) for key in MONEY}, status=status))
    for order in orders.values():
        order["payment"] = payment_from_items(order.pop("_items"))
    return orders


def payment_from_items(items):
    """Shipping and seller discount of one order (cancelled items left out)."""
    active = [i for i in items if i["status"] not in CANCELLED] or items
    if all(i[key] is None for i in active for key in MONEY):
        return False

    def total(key):
        return sum(i[key] or 0.0 for i in active)

    return {
        "source": "excel",
        "products_total": total("unit_price"),
        "shipping": total("shipping_fee"),
        "voucher_amount": abs(total("seller_discount")),
        "voucher_codes": [],
        "fees": [],
        "net_income": None,
    }
