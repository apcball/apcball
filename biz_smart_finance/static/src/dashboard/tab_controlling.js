/** @odoo-module **/

import { BsfTab, buildStackedBar, LEVEL_COLORS } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

// ชื่อไทยของประเภทบัญชีที่โผล่ในมุมมองต้นทุน (นอกเหนือจากนี้โชว์รหัสดิบ)
const ACCOUNT_TYPE_LABELS = {
    expense: "ค่าใช้จ่ายดำเนินงาน",
    expense_direct_cost: "ต้นทุนขาย/บริการ",
    expense_depreciation: "ค่าเสื่อมราคา",
    income: "รายได้",
    income_other: "รายได้อื่น",
    asset_fixed: "สินทรัพย์ถาวร",
    asset_current: "สินทรัพย์หมุนเวียน",
};

const TYPE_COLORS = ["#38bdf8", "#6366f1", "#a855f7", "#f97316", "#22c55e", "#64748b"];

/**
 * Controlling (SAP CO) — ศูนย์ต้นทุน × งบประมาณ × ภาระผูกพัน
 * Available = งบ − ใช้จริง − ภาระผูกพัน (PO ที่ยืนยันแล้วยังไม่ตั้งบิล)
 */
export class BsfTabControlling extends BsfTab {
    static template = "biz_smart_finance.TabControlling";
    static components = { BsfAiCard };
    static props = { data: Object, unit: String, onPlan: Function };

    get co() {
        return this.props.data.controlling;
    }

    /** แถบสัดส่วนต้นทุนตามประเภทบัญชี GL */
    get typeBar() {
        const rows = this.co.by_account_type;
        return buildStackedBar(
            rows.map((r) => Math.abs(r.amount)), TYPE_COLORS,
        ).map((seg, index) => ({
            ...seg,
            amount: rows[index].amount,
            label: this.typeLabel(rows[index].account_type),
        }));
    }

    typeLabel(code) {
        return ACCOUNT_TYPE_LABELS[code] || code;
    }

    /** ความยาวหลอด utilization (ตัดที่ 100% แต่คงสีเตือนถ้าเกิน) */
    barWidth(row) {
        const pct = row.utilization_pct;
        if (pct === null || pct === undefined) {
            return 0;
        }
        return Math.max(0, Math.min(Number(pct), 100));
    }

    barColor(row) {
        const pct = Number(row.utilization_pct || 0);
        if (row.over_budget || pct > 100) {
            return LEVEL_COLORS.high;
        }
        return pct >= 85 ? LEVEL_COLORS.medium : LEVEL_COLORS.low;
    }

    onPlanChange(ev) {
        this.props.onPlan(parseInt(ev.target.value, 10));
    }

    // ---------------- drill-downs ----------------
    /** แถวศูนย์ต้นทุน → analytic line ของศูนย์นั้นในช่วงปีงบถึง as-of */
    openAnalyticLines(row) {
        const column = this.co.column;
        if (!column) {
            return;
        }
        this.openList(row.name, "account.analytic.line", [
            [column, "=", row.analytic_id],
            ["date", ">=", this.co.date_from],
            ["date", "<=", this.co.date_to],
            ...this.companyDomain(),
        ]);
    }

    /** ช่องภาระผูกพัน → PO ที่ยืนยันแล้วยังตั้งบิลไม่ครบ */
    openCommitment(row) {
        this.openList(`ภาระผูกพัน · ${row.name}`, "purchase.order.line", [
            ["state", "in", ["purchase", "done"]],
            ["analytic_distribution", "in", [row.analytic_id]],
            ...this.companyDomain(),
        ]);
    }

    /** ช่องงบประมาณ → บรรทัดงบของศูนย์ต้นทุนนั้น (ตามแหล่งที่ตั้งไว้) */
    openBudget(row) {
        if (!this.co.budget_available) {
            return;
        }
        const model = this.co.budget_source === "external"
            ? "biz.smart.finance.ext.budget"
            : "crossovered.budget.lines";
        this.openList(`งบประมาณ · ${row.name}`, model, [
            ["analytic_account_id", "=", row.analytic_id],
            ["date_from", "<=", this.co.date_to],
            ["date_to", ">=", this.co.date_from],
        ]);
    }

    /** ป้ายบอกว่างบก้อนนี้มาจากไหน (ต่อบริษัท เลือกได้ใน Settings) */
    get budgetSourceLabel() {
        return {
            odoo: "Odoo Budget",
            external: "ระบบภายนอก",
            mixed: "ผสม Odoo + ภายนอก",
        }[this.co.budget_source] || "Odoo Budget";
    }

    openAllBudgets() {
        if (!this.co.budget_available) {
            return;
        }
        if (this.co.budget_source === "external") {
            this.openList(
                "งบศูนย์ต้นทุน (ระบบภายนอก)",
                "biz.smart.finance.ext.budget", this.companyDomain());
            return;
        }
        this.openList("งบประมาณทั้งหมด", "crossovered.budget", []);
    }
}
