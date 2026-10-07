/** @odoo-module **/
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";

export class LandedCostListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    onClickExportExcel() {
        const domain = this.model.root.domain;
        this.actionService.doAction("buz_landed_cost_report.action_lc_export_wizard", {
            additionalContext: { default_domain_json: JSON.stringify(domain) },
        });
    }
}

registry.category("views").add("buz_lc_report_list", {
    ...listView,
    Controller: LandedCostListController,
    buttonTemplate: "buz_landed_cost_report.ListView.Buttons",
});
