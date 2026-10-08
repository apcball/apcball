/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Many2OneField, many2OneField } from "@web/views/fields/many2one/many2one_field";

// Many2one that shows a second, muted line (e.g. the product Internal
// Reference) read from the field named in options.subtitle_field.
export class LazadaMany2OneSubtitleField extends Many2OneField {
    static template = "lazada_connector.Many2OneSubtitleField";
    static props = {
        ...Many2OneField.props,
        subtitleField: { type: String },
    };

    get subtitle() {
        return this.value ? this.props.record.data[this.props.subtitleField] || "" : "";
    }
}

export const many2OneSubtitleField = {
    ...many2OneField,
    component: LazadaMany2OneSubtitleField,
    fieldDependencies: ({ options }) => [{ name: options.subtitle_field, type: "char" }],
    extractProps(fieldInfo, dynamicInfo) {
        return {
            ...many2OneField.extractProps(fieldInfo, dynamicInfo),
            subtitleField: fieldInfo.options.subtitle_field,
        };
    },
};

registry.category("fields").add("lazada_many2one_subtitle", many2OneSubtitleField);
