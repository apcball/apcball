/** @odoo-module **/

import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { KanbanRecord } from "@web/views/kanban/kanban_record";

export class ProductKanbanRecord extends KanbanRecord {
    setup() {
        super.setup();
    }

    calculatePriceWithVat(price) {
        const priceValue = parseFloat(price);
        if (!isNaN(priceValue)) {
            return (priceValue * 1.07).toFixed(2);
        }
        return "0.00";
    }
}

registry.category("views").add("product_kanban_vat", {
    ...kanbanView,
    Record: ProductKanbanRecord,
});