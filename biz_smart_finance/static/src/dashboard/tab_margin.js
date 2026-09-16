/** @odoo-module **/

import { BsfTab, buildScatter } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

export class BsfTabMargin extends BsfTab {
    static template = "biz_smart_finance.TabMargin";
    static components = { BsfAiCard };

    get margin() {
        return this.props.data.margin;
    }

    get scatter() {
        return this.memoChart("scatter", [this.margin, this.unit], () =>
            buildScatter(this.margin.bubbles, { width: 560, height: 340 }));
    }

    openProject(row) {
        if (row.project_id) {
            this.openForm("project.project", row.project_id);
        }
    }

    openVo(row) {
        if (row.id) {
            this.openForm("biz.smart.finance.vo", row.id);
        }
    }

    openVoList() {
        this.openList("Variation Orders", "biz.smart.finance.vo", []);
    }

    openProjects() {
        this.openList("โครงการทั้งหมด", "project.project", [
            ["active", "=", true],
            ...this.companyDomain(),
        ]);
    }

    voStateLabel(state) {
        return { pending: "Pending", approved: "Approved", rejected: "Rejected" }[state] || state;
    }
}
