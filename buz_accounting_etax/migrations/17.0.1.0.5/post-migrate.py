from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Backfill wrong deposit values on draft e-tax transactions.

    Older records could get a deposit amount from the fallback heuristic that
    treated any `ordered_prepaid` product as a down payment. That makes
    `total_after_deposit` collapse to zero for normal invoices.

    We only reset draft transactions when the source invoice is not a genuine
    down payment invoice:
    - no invoice line is flagged as `is_downpayment`
    - invoice `advance_payment_method` is not `percentage` or `fixed`
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    transactions = env["etax.transaction"].search([
        ("state", "=", "draft"),
        ("deposit", ">", 0.0),
        ("invoice_id", "!=", False),
    ])

    fixed_count = 0
    skipped_downpayment = 0

    for transaction in transactions:
        invoice = transaction.invoice_id
        if not invoice:
            continue

        has_downpayment_line = any(line.is_downpayment for line in invoice.invoice_line_ids)
        is_explicit_downpayment = invoice.advance_payment_method in ("percentage", "fixed")

        if has_downpayment_line or is_explicit_downpayment:
            skipped_downpayment += 1
            continue

        transaction.write({"deposit": 0.0})
        fixed_count += 1

    # Keep the migration visible in server logs for traceability.
    print(
        "buz_accounting_etax post-migrate: reset deposit on "
        f"{fixed_count} draft transaction(s); skipped {skipped_downpayment} "
        "explicit down payment transaction(s)."
    )
