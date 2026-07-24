/** @odoo-module **/
import { registry } from "@web/core/registry";
QUnit.module("mogen_sop_ai Copilot");
QUnit.test("Copilot client action is registered", (assert) => assert.ok(registry.category("actions").contains("mogen_sop_ai.copilot")));
