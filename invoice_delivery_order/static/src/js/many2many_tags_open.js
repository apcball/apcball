/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    Many2ManyTagsField,
    many2ManyTagsField,
} from "@web/views/fields/many2many_tags/many2many_tags_field";

class Many2ManyTagsOpenField extends Many2ManyTagsField {
    setup() {
        super.setup();
        this.action = useService("action");
    }

    getTagProps(record) {
        return {
            ...super.getTagProps(record),
            onClick: () => this.action.doAction({
                type: "ir.actions.act_window",
                res_model: this.relation,
                res_id: record.resId,
                views: [[false, "form"]],
                target: "current",
            }),
        };
    }
}

registry.category("fields").add("many2many_tags_open", {
    ...many2ManyTagsField,
    component: Many2ManyTagsOpenField,
});
