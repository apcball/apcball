/** @odoo-module **/

import { BsfTab, FUNNEL_COLORS } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

export class BsfTabSales extends BsfTab {
    static template = "biz_smart_finance.TabSales";
    static components = { BsfAiCard };

    get sales() {
        return this.props.data.sales;
    }

    stageColor(index) {
        return FUNNEL_COLORS[index % FUNNEL_COLORS.length];
    }

    stageIcon(code) {
        return {
            booking: "fa-handshake-o",
            backlog: "fa-tasks",
            production: "fa-industry",
            install: "fa-wrench",
            invoice: "fa-file-text-o",
            collection: "fa-money",
        }[code] || "fa-circle";
    }

    // ---------------- drill-downs ----------------
    get soDateDomain() {
        return [
            ["date_order", ">=", this.fyFrom],
            ["date_order", "<=", `${this.fyTo} 23:59:59`],
        ];
    }

    /** funnel แต่ละขั้นกดเจาะไปเอกสารต้นทางของขั้นนั้น */
    openStage(stage) {
        const name = `${stage.label} (YTD)`;
        switch (stage.stage) {
            case "booking":
                this.openList(name, "sale.order", [
                    ["state", "=", "sale"],
                    ...this.soDateDomain,
                    ...this.companyDomain(),
                ]);
                break;
            case "backlog":
                this.openList(name, "sale.order", [
                    ["state", "=", "sale"],
                    ["invoice_status", "in", ["to invoice", "no"]],
                    ...this.companyDomain(),
                ]);
                break;
            case "production":
                this.openList(name, "project.task", [
                    ["boq_task_kind", "in",
                     ["produce", "pr", "po", "sub_pr", "sub_po"]],
                    ...this.companyDomain("project_id.company_id"),
                ]);
                break;
            case "install":
                this.openList(name, "project.task", [
                    ["boq_task_kind", "in", ["install", "inspect"]],
                    ...this.companyDomain("project_id.company_id"),
                ]);
                break;
            case "invoice":
                this.openMoves(name, ["out_invoice", "out_refund"]);
                break;
            case "collection":
                this.openList(name, "account.payment", [
                    ["payment_type", "=", "inbound"],
                    ["partner_type", "=", "customer"],
                    ["state", "=", "posted"],
                    ["date", ">=", this.fyFrom],
                    ["date", "<=", this.fyTo],
                    ...this.companyDomain(),
                ]);
                break;
        }
    }

    openChannel(row) {
        this.openList(`ยอดขาย · ${row.name}`, "sale.order", [
            ["state", "=", "sale"],
            ["team_id", "=", row.key || false],
            ...this.soDateDomain,
            ...this.companyDomain(),
        ]);
    }

    openBu(row) {
        this.openList(`ยอดขาย · ${row.name}`, "sale.order", [
            ["state", "=", "sale"],
            ["company_id", "=", row.key],
            ...this.soDateDomain,
        ]);
    }

    openTotalAr() {
        this.openOpenMovesDue("ลูกหนี้คงค้างทั้งหมด", ["out_invoice"]);
    }

    openOverdueAr() {
        // เกิน 60 วัน = ครบกำหนดก่อน (วันนี้ − 61 วัน)
        this.openOpenMovesDue(
            "ลูกหนี้ค้างเกิน 60 วัน", ["out_invoice"],
            false, this.dateOffset(this.echoFilters.today, -61));
    }
}
