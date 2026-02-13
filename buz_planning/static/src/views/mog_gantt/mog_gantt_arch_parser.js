/** @odoo-module **/

import { visitXML } from "@web/core/utils/xml";

export class MogGanttArchParser {
    parse(arch, fields) {
        const archInfo = {
            dateStartField: null,
            dateStopField: null,
            defaultGroupBy: "employee_id",
            colorField: "",
            fieldNames: [],
        };

        if (fields && fields.display_name) {
            archInfo.fieldNames.push("display_name");
        }

        visitXML(arch, (node) => {
            switch (node.tagName) {
                case "mog_gantt": {
                    archInfo.dateStartField = node.getAttribute("date_start");
                    archInfo.dateStopField = node.getAttribute("date_stop");
                    if (node.hasAttribute("default_group_by")) {
                        archInfo.defaultGroupBy = node.getAttribute("default_group_by");
                    }
                    if (node.hasAttribute("color")) {
                        archInfo.colorField = node.getAttribute("color");
                    }
                    break;
                }
                case "field": {
                    const fieldName = node.getAttribute("name");
                    if (fieldName && !archInfo.fieldNames.includes(fieldName)) {
                        archInfo.fieldNames.push(fieldName);
                    }
                    break;
                }
            }
        });

        // Ensure date fields are in fieldNames
        const extraFields = [
            archInfo.dateStartField,
            archInfo.dateStopField,
            archInfo.defaultGroupBy,
            archInfo.colorField,
        ];
        for (const f of extraFields) {
            if (f && !archInfo.fieldNames.includes(f)) {
                archInfo.fieldNames.push(f);
            }
        }

        archInfo.fields = fields || {};
        archInfo.resModel = null; // set by view props
        return archInfo;
    }
}
