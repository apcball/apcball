"""Run through Odoo shell ONLY on the disposable QA database.

Unlike TransactionCase, these checks use independent PostgreSQL transactions.
Fixtures are committed solely to test cross-connection visibility and removed
in finally. Every external operation is mocked.
"""
from unittest.mock import Mock, patch

from odoo import api, fields, SUPERUSER_ID
from odoo.addons.shopee_connector.models.shopee_api import ShopeeAPIError

assert env.cr.dbname == "MOG_TEST_SHOPEE", "Refusing to run outside isolated Shopee QA"


def cleanup_fixture(config):
    """Also recover this exact synthetic fixture after an interrupted run."""
    config.ensure_one()
    assert config.name == "QA concurrency" and config.shop_id == "QA-CONCURRENCY"
    orders = env["sale.order"].search([("shopee_config_id", "=", config.id)])
    partners = orders.partner_id
    products = orders.order_line.product_id
    env["shopee.fulfillment.job"].search([("config_id", "=", config.id)]).unlink()
    orders._action_cancel()
    orders.unlink()
    config.unlink()
    partners.unlink()
    products.unlink()
    env.cr.commit()


previous = env["shopee.config"].search([("shop_id", "=", "QA-CONCURRENCY")])
if previous:
    cleanup_fixture(previous)
config = env["shopee.config"].create({
    "name": "QA concurrency", "partner_id": "100", "partner_key": "qa-only",
    "shop_id": "QA-CONCURRENCY", "access_token": "qa-only",
    "token_expires_at": "2999-01-01 00:00:00",
})
job = env["shopee.retry.queue"].enqueue(config, "sync_order", {"order_sn": "QA-CONCURRENT"})
partner = env["res.partner"].with_context(skip_partner_required_fields=True).create({"name": "QA concurrency buyer"})
product = env["product.product"].create({"name": "QA concurrency service", "default_code": "QA-CONCURRENT", "type": "service"})
order = env["sale.order"].create({
    "partner_id": partner.id, "shopee_config_id": config.id,
    "is_shopee_order": True, "shopee_order_sn": "QA-SHIP-TIMEOUT",
    "order_line": [fields.Command.create({"product_id": product.id, "product_uom_qty": 1})],
})
shipment = env["shopee.fulfillment.job"].create({"order_id": order.id})
env.cr.commit()
try:
    with env.registry.cursor() as owner, env.registry.cursor() as contender:
        owner.execute("SELECT id FROM shopee_retry_queue WHERE id = %s FOR UPDATE", [job.id])
        other_env = api.Environment(contender, SUPERUSER_ID, {})
        with patch.object(type(config), "import_order_by_sn") as operation:
            other_env["shopee.retry.queue"].browse(job.id)._run_one()
            operation.assert_not_called()
        contender.rollback()
        owner.rollback()
    with env.registry.cursor() as worker:
        worker_env = api.Environment(worker, SUPERUSER_ID, {})
        with patch.object(type(config), "import_order_by_sn", return_value=True) as operation:
            worker_env["shopee.retry.queue"].browse(job.id)._run_one()
            worker.commit()
            worker_env["shopee.retry.queue"].browse(job.id)._run_one()
            assert operation.call_count == 1, "Completed retry was replayed"
        worker.rollback()
    print("PASS: retry lock excludes a second connection; completed job is not replayed")

    # A shipment intent must survive rollback after an ambiguous API timeout.
    client = Mock()
    client.get_order_detail.return_value = {"response": {"order_list": [{
        "order_sn": order.shopee_order_sn, "order_status": "READY_TO_SHIP",
    }]}}
    client.get_shipping_parameter.return_value = {"response": {"info_needed": {"dropoff": []}}}
    client.ship_order.side_effect = ShopeeAPIError("network", "Timeout")
    shipment._prepare(client, "qa-only")
    shipment.option_id = shipment.option_ids[0]
    order.action_confirm()
    try:
        shipment._ship(client, "qa-only")
        raise AssertionError("Expected ambiguous timeout")
    except ShopeeAPIError:
        env.cr.rollback()
    shipment.invalidate_recordset()
    assert shipment.state == "uncertain" and shipment.shipment_requested_at
    shipment._ship(client, "qa-only")
    assert client.ship_order.call_count == 1, "Ambiguous shipment was resent"
    print("PASS: shipment intent survives rollback; timeout does not resend shipment")

    with env.registry.cursor() as owner, env.registry.cursor() as contender:
        owner.execute("SELECT pg_try_advisory_lock(%s, %s)", [734291, shipment.id])
        assert owner.fetchone()[0]
        try:
            owner.commit()
            contender.execute("SELECT pg_try_advisory_lock(%s, %s)", [734291, shipment.id])
            assert not contender.fetchone()[0], "Shipping lock did not survive intent commit"
        finally:
            owner.execute("SELECT pg_advisory_unlock(%s, %s)", [734291, shipment.id])
    print("PASS: fulfillment session lock survives intent commit")
finally:
    env.cr.rollback()
    env.invalidate_all()
    cleanup_fixture(config)
