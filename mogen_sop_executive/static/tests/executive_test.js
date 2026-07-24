/** @odoo-module **/
import { registry } from "@web/core/registry";
QUnit.module("mogen_sop_executive Decision Center");
QUnit.test("Decision Center client action is registered", (assert) => assert.ok(registry.category("actions").contains("mogen_sop_executive.decision_center")));
