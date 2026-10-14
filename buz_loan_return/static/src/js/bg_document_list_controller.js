/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

class BuzLoanReturnDocumentListController extends ListController {
    setup() {
        super.setup();
        this.action = useService("action");
    }

    onNewBg() {
        return this.action.doAction("buz_loan_return.action_buz_loan_return_create_bg");
    }
}

registry.category("views").add("buz_loan_return_document_list", {
    ...listView,
    Controller: BuzLoanReturnDocumentListController,
    buttonTemplate: "buz_loan_return.BGDocumentListButtons",
});