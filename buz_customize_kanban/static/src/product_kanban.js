/** @odoo-module **/

import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRecord } from "@web/views/kanban/kanban_record";

class ProductKanbanRecord extends KanbanRecord {
    static template = "buz_customize_kanban.KanbanRecord";
}

registry.category("views").add("product_kanban_vat", {
    ...kanbanView,
    buttonTemplate: "product_kanban_vat.RecordButtons",
    Record: ProductKanbanRecord,
});