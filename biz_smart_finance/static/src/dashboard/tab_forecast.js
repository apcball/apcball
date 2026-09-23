/** @odoo-module **/

import { useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { BsfTab, buildCashChart } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

/**
 * แท็บพยากรณ์รายเดือน — สี่มุมมองในแท็บเดียว (เงินสด / P&L / งานขาย / ต้นทุนคงเหลือ)
 * ทั้งสี่ใช้ payload ก้อนเดียวและกริดเดือนชุดเดียวกัน จึงไม่แยกเป็นสี่แท็บ
 */
export class BsfTabForecast extends BsfTab {
    static template = "biz_smart_finance.TabForecast";
    static components = { BsfAiCard };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ section: "cash", drafting: false });
    }

    get forecast() {
        return this.props.data.forecast;
    }

    get months() {
        return this.forecast.months;
    }

    get sections() {
        return [
            { id: "cash", label: "เงินสดรายเดือน", icon: "fa-line-chart" },
            { id: "pnl", label: "กำไรขาดทุน", icon: "fa-table" },
            { id: "pipeline", label: "งานขาย", icon: "fa-filter" },
            { id: "ctc", label: "ต้นทุนคงเหลือ", icon: "fa-tasks" },
        ];
    }

    setSection(id) {
        this.state.section = id;
    }

    get isManager() {
        return !!(this.props.data.ai && this.props.data.ai.is_manager);
    }

    get aiConfigured() {
        return !!(this.props.data.ai && this.props.data.ai.configured);
    }

    // ---------------- เงินสด ----------------
    get cash() {
        return this.forecast.cash;
    }

    get cashChart() {
        return this.memoChart(
            "cashChart", [this.cash, this.months, this.unit], () => {
                const cash = this.cash;
                return buildCashChart(
                    this.months.map((m) => m.label),
                    cash.closing.map((v) => this.scale(v)),
                    {
                        minCash: this.scale(cash.min_cash),
                        dividerIndex: 0, height: 280,
                    },
                );
            });
    }

    /** แถวตารางเงินสด — ชั้น 1 (ผูกพันแล้ว) แยกสายตาจากชั้น 2 (ถ่วงน้ำหนัก) */
    get cashRows() {
        return [
            { key: "opening", label: "เงินสดยกมา", sign: 1, drill: "" },
            { key: "in_collections", label: "· เก็บเงินตามสัญญา/ลูกหนี้", sign: 1, drill: "ar" },
            { key: "in_sales_to_cash", label: "· Sales to Cash (SO ยังไม่วางบิล)", sign: 1, drill: "" },
            { key: "in_pipeline", label: "· งานขาย (ถ่วงน้ำหนัก)", sign: 1, drill: "deal", layer2: true },
            { key: "in_other", label: "· เงินเข้าอื่น (กรอกมือ)", sign: 1, drill: "lines" },
            { key: "out_ap", label: "· เจ้าหนี้/แผนจ่ายผู้รับเหมา/PO", sign: -1, drill: "ap" },
            { key: "out_boq", label: "· งบ BOQ ที่ยังไม่เปิด PO", sign: -1, drill: "" },
            { key: "out_pipeline", label: "· ต้นทุนงานขาย (ถ่วงน้ำหนัก)", sign: -1, drill: "deal", layer2: true },
            { key: "out_payroll_opex", label: "· เงินเดือน/ค่าใช้จ่าย", sign: -1, drill: "lines" },
            { key: "out_tax_other", label: "· ภาษี/อื่น ๆ", sign: -1, drill: "lines" },
            { key: "net", label: "กระแสเงินสดสุทธิ", sign: 1, drill: "" },
            { key: "closing", label: "เงินสดคงเหลือ", sign: 1, drill: "" },
        ];
    }

    /** ยอดรวมทั้งช่วงของแถวหนึ่ง — ยอดยกมา/คงเหลือรวมกันไม่ได้ (เป็นยอด ณ จุดเวลา) */
    cashTotal(metric) {
        if (metric.key === "opening" || metric.key === "closing") {
            return "—";
        }
        const total = this.cash.rows.reduce(
            (sum, row) => sum + (row[metric.key] || 0), 0);
        return metric.sign < 0 && total
            ? `(${this.fmtMoney(total)})`
            : this.fmtMoney(total);
    }

    openCashDrill(metric, row) {
        if (!metric.drill) {
            return;
        }
        if (metric.drill === "lines") {
            this.openForecastLines();
            return;
        }
        if (metric.drill === "deal") {
            this.openDeals();
            return;
        }
        const month = this.months[row.index] || {};
        // เดือนแรกรวมยอดเกินกำหนดไว้ด้วย จึงไม่กำหนดขอบล่าง; คอลัมน์ท้าย
        // ไม่มีขอบบน (ดูดทุกอย่างหลัง horizon)
        const dateFrom = row.index === 0 ? false : month.date_from;
        const dateTo = month.is_tail ? false : month.date_to;
        if (metric.drill === "ar") {
            this.openOpenMovesDue(
                `ลูกหนี้ครบกำหนด ${row.label}`, ["out_invoice"], dateFrom, dateTo);
        } else {
            this.openOpenMovesDue(
                `เจ้าหนี้ครบกำหนด ${row.label}`, ["in_invoice"], dateFrom, dateTo);
        }
    }

    // ---------------- กำไรขาดทุน ----------------
    get pnl() {
        return this.forecast.pnl;
    }

    get pnlRows() {
        return [
            { key: "revenue_backlog", label: "รายได้จากงานที่เซ็นแล้ว", kind: "money" },
            { key: "revenue_pipeline", label: "รายได้จากงานขาย (ถ่วงน้ำหนัก)", kind: "money", layer2: true },
            { key: "other_income", label: "รายได้อื่น (กรอกมือ)", kind: "money" },
            { key: "revenue", label: "รวมรายได้", kind: "money", strong: true },
            { key: "cost_project", label: "ต้นทุนโครงการคงเหลือ", kind: "money", negative: true },
            { key: "cost_pipeline", label: "ต้นทุนงานขาย (ถ่วงน้ำหนัก)", kind: "money", negative: true, layer2: true },
            { key: "opex", label: "ค่าใช้จ่ายประจำ", kind: "money", negative: true },
            { key: "cost", label: "รวมต้นทุน+ค่าใช้จ่าย", kind: "money", negative: true, strong: true },
            { key: "margin", label: "กำไรคาดการณ์", kind: "money", strong: true },
            { key: "margin_pct", label: "อัตรากำไร (%)", kind: "pct" },
        ];
    }

    pnlCell(row, index) {
        const series = this.pnl[row.key] || [];
        const value = series[index];
        if (row.kind === "pct") {
            return this.fmtPct(value);
        }
        if (row.negative && value) {
            return `(${this.fmtMoney(value)})`;
        }
        return this.fmtMoney(value);
    }

    pnlTotal(row) {
        if (row.kind === "pct") {
            return this.fmtPct(this.pnl.total.margin_pct);
        }
        const series = this.pnl[row.key] || [];
        const total = series.reduce((sum, v) => sum + (v || 0), 0);
        return row.negative && total
            ? `(${this.fmtMoney(total)})`
            : this.fmtMoney(total);
    }

    // ---------------- งานขาย ----------------
    get pipeline() {
        return this.forecast.pipeline;
    }

    openDeals() {
        this.openList(
            "งานขาย (Pipeline)", "biz.smart.finance.deal",
            [["stage", "in", ["lead", "proposal", "nego"]]]);
    }

    openDeal(dealId) {
        this.openForm("biz.smart.finance.deal", dealId);
    }

    // ---------------- ต้นทุนคงเหลือ ----------------
    get ctc() {
        return this.forecast.ctc;
    }

    openProject(projectId) {
        this.openForm("project.project", projectId);
    }

    // ---------------- รายการกรอกมือ / AI ----------------
    openForecastLines() {
        this.openList(
            "รายการกระแสเงินสดประจำ", "biz.smart.finance.forecast.line",
            [["state", "=", "confirmed"]]);
    }

    openDraftLines() {
        this.openList(
            "ร่างจาก AI (รอยืนยัน)", "biz.smart.finance.forecast.line",
            [["state", "=", "draft"]]);
    }

    async draftWithAi() {
        if (this.state.drafting) {
            return;
        }
        this.state.drafting = true;
        try {
            const filters = this.echoFilters;
            const result = await this.orm.call(
                "biz.smart.finance.ai", "suggest_forecast",
                [{
                    company_id: filters.company_id,
                    year: filters.year,
                    month: filters.month,
                    scenario: filters.scenario,
                }],
            );
            this.notification.add(
                result.summary || "AI ร่างรายการให้แล้ว",
                {
                    title: `สร้างร่าง ${result.created} รายการ (ข้าม ${result.skipped})`,
                    type: "success",
                },
            );
            if (result.created) {
                this.openDraftLines();
            }
        } catch (error) {
            this.notification.add(
                error.data && error.data.message ? error.data.message : String(error),
                { title: "AI ร่าง forecast ไม่สำเร็จ", type: "danger" },
            );
        } finally {
            this.state.drafting = false;
        }
    }
}
