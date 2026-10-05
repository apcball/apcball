"""Seed with the original addon; verify after upgrading to the patched addon."""
import os

assert env.cr.dbname == "MOG_TEST_SHOPEE_UPGRADE", "Only run on the disposable upgrade database"
Config = env["shopee.config"]
config = Config.search([("shop_id", "=", "QA-UPGRADE-SEED")])
if os.environ["SHOPEE_QA_UPGRADE_MODE"] == "seed-upgrade":
    assert not config, "Upgrade fixture already exists"
    config = Config.create({
        "name": "Upgrade fixture", "partner_id": "100", "partner_key": "qa-fixture-key",
        "shop_id": "QA-UPGRADE-SEED", "active": False,
    })
    product = env["product.product"].create({"name": "Upgrade fixture", "default_code": "QA-UPGRADE-SEED"})
    env["shopee.product.mapping"].create({
        "shopee_config_id": config.id, "product_id": product.id,
        "shopee_sku": "QA-UPGRADE-SEED", "shopee_item_id": "900", "shopee_stock": 17,
    })
    env["shopee.retry.queue"].enqueue(config, "sync_order", {"order_sn": "QA-UPGRADE-SEED"}).write({"attempts": 2})
    env["shopee.api.log"].create_api_log(config, endpoint="/qa-upgrade", response_data={"fixture": True})
    env.cr.commit()
    print("PASS: committed original-schema upgrade fixtures")
else:
    config = Config.with_context(active_test=False).search([("shop_id", "=", "QA-UPGRADE-SEED")])
    assert len(config) == 1 and config.name == "Upgrade fixture"
    assert config.partner_key == "qa-fixture-key" and not config.active
    mapping = env["shopee.product.mapping"].search([("shopee_config_id", "=", config.id)])
    assert len(mapping) == 1 and mapping.shopee_stock == 17 and mapping.shopee_item_id == "900"
    assert mapping.product_id.default_code == "QA-UPGRADE-SEED"
    retry = env["shopee.retry.queue"].search([("shopee_config_id", "=", config.id)])
    assert len(retry) == 1 and retry.state == "pending" and retry.attempts == 2
    assert retry.company_id == config.company_id
    log = env["shopee.api.log"].search([("shopee_config_id", "=", config.id)])
    assert len(log) == 1 and log.endpoint == "/qa-upgrade"
    assert log.company_id == config.company_id
    assert not config.oauth_state_expires_at
    print("PASS: upgrade preserved config, mapping, stock, retry and log; company fields backfilled")
