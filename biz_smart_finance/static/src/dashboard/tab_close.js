/** @odoo-module **/

import { BsfTab } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

const STATE_LABELS = {
    open: "เปิดอยู่", review: "รอตรวจสอบ", closed: "ปิดงวดแล้ว",
};
const SOURCE_LABELS = { odoo: "Odoo", external: "ภายนอก" };
const SOURCE_FIELDS = [
    ["gl_source", "GL"],
    ["invoice_source", "ใบแจ้งหนี้"],
    ["inventory_source", "สต๊อก"],
    ["ratio_source", "อัตราส่วน"],
    ["budget_source", "งบ"],
];

export class BsfTabClose extends BsfTab {
    static template = "biz_smart_finance.TabClose";
    static components = { BsfAiCard };

    get close() {
        return this.props.data.close;
    }

    get sourceFields() {
        return SOURCE_FIELDS;
    }

    stateLabel(state) {
        return STATE_LABELS[state] || state;
    }

    sourceLabel(source) {
        return SOURCE_LABELS[source] || source;
    }

    sourceColor(source) {
        return source === "external" ? "#fbbf24" : "#cbd5e1";
    }

    stateColor(state) {
        if (state === "closed") return "#86efac";
        if (state === "review") return "#93c5fd";
        return "#e2e8f0";
    }

    /** แถวที่ยังไม่มีทะเบียนงวด → เปิดฟอร์มใหม่พร้อม default ของงวดนั้น
     * แถวที่มีอยู่แล้ว → เปิดฟอร์มเดิม (มีปุ่มตั้งแหล่งข้อมูล/ปิดงวดในนั้น) */
    openPeriod(row) {
        if (row.period_id) {
            this.openForm("biz.smart.finance.period", row.period_id);
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "biz.smart.finance.period",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_company_id: row.company_id,
                default_date_from: row.date_from,
                default_date_to: row.date_to,
            },
        });
    }

    openGenerateWizard() {
        this.action.doAction("biz_smart_finance.action_bsf_period_generate_wizard");
    }

    openTbImport() {
        this.action.doAction("biz_smart_finance.action_bsf_tb_import");
    }

    openExtGl(companyId) {
        const domain = companyId ? [["company_id", "=", companyId]] : [];
        this.openList("Trial Balance ภายนอก", "biz.smart.finance.ext.gl", domain);
    }
}
