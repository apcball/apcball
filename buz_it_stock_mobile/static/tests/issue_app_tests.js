/** @odoo-module **/
import { itemKey, quantityTotals } from "@buz_it_stock_mobile/issue_app";

QUnit.module("IT Issue Mobile");
QUnit.test("serials remain separate cart entries", (assert) => {
    assert.notEqual(itemKey(7, 10), itemKey(7, 11));
    assert.equal(itemKey(7), itemKey(7, false));
});
QUnit.test("totals never combine incompatible units", (assert) => {
    assert.equal(quantityTotals([
        { quantity: 2, uom: "ชิ้น" }, { quantity: 1, uom: "ชิ้น" },
        { quantity: 1.5, uom: "เมตร" },
    ]), "3 ชิ้น · 1.5 เมตร");
});
