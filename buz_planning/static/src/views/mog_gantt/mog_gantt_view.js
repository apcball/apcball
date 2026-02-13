/** @odoo-module **/

import { registry } from "@web/core/registry";
import { MogGanttController } from "./mog_gantt_controller";
import { MogGanttModel } from "./mog_gantt_model";
import { MogGanttRenderer } from "./mog_gantt_renderer";
import { MogGanttArchParser } from "./mog_gantt_arch_parser";

const viewRegistry = registry.category("views");

export const mogGanttView = {
    type: "mog_gantt",
    display_name: "Gantt",
    icon: "fa fa-tasks",
    multiRecord: true,
    Controller: MogGanttController,
    Model: MogGanttModel,
    Renderer: MogGanttRenderer,
    ArchParser: MogGanttArchParser,

    props: (genericProps, view) => {
        const { arch, fields, resModel } = genericProps;
        const parser = new view.ArchParser();
        const archInfo = parser.parse(arch, fields);
        const modelParams = {
            ...archInfo,
            resModel: resModel,
            fields: fields,
        };

        return {
            ...genericProps,
            modelParams,
            Model: view.Model,
            Renderer: view.Renderer,
        };
    },
};

viewRegistry.add("mog_gantt", mogGanttView);
