/** @odoo-module **/
import { itemKey, quantityTotals, categoryChart } from "@buz_it_stock_mobile/issue_app";

QUnit.module("IT Issue Mobile");
QUnit.test("serials remain separate cart entries", (assert) => {
    assert.notEqual(itemKey(7, 10), itemKey(7, 11));
    assert.equal(itemKey(7), itemKey(7, false));
});
QUnit.test("dashboard charts use actual quantities and never mix units", (assert) => {
    assert.strictEqual(categoryChart([]), null);
    assert.strictEqual(categoryChart([{ qty: 0, uom: "ชิ้น" }]), null);
    assert.strictEqual(categoryChart([{ qty: 2, uom: "ชิ้น" }, { qty: 3, uom: "เมตร" }]), null);
    const chart = categoryChart([{ qty: 3, uom: "ชิ้น" }, { qty: 1, uom: "ชิ้น" }]);
    assert.equal(chart.total, 4);
    assert.equal(chart.uom, "ชิ้น");
    assert.ok(chart.style.includes("0% 75%"), "first segment is proportional to quantity");
    assert.ok(chart.style.includes("75% 100%"), "last segment completes the circle");
});
QUnit.test("totals never combine incompatible units", (assert) => {
    assert.equal(quantityTotals([
        { quantity: 2, uom: "ชิ้น" }, { quantity: 1, uom: "ชิ้น" },
        { quantity: 1.5, uom: "เมตร" },
    ]), "3 ชิ้น · 1.5 เมตร");
});
