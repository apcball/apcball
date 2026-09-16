/** @odoo-module **/

import { useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { BsfTab, buildCashChart, LEVEL_COLORS } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

const PURPOSE_LABELS = {
    liquidity: "Liquidity Support",
    working_capital: "Working Capital",
    cash_pool: "Cash Pool Balancing",
    debt_service: "Debt Service",
    other: "อื่น ๆ",
};

const TRANSFER_STATE_LABELS = {
    draft: "รออนุมัติ",
    approved: "อนุมัติแล้ว",
    done: "โอนแล้ว",
    cancel: "ยกเลิก",
};

const BANK_STATUS_LABELS = {
    on_track: "On Track",
    monitor: "Monitor",
    at_risk: "At Risk",
};

const FACILITY_STATUS_LABELS = {
    healthy: "Healthy",
    monitor: "Monitor",
    risk: "At Risk",
};

const SHARES_BASIS_LABELS = {
    history: "คิดจากประวัติเดินบัญชีย้อนหลัง",
    override: "มีธนาคารตั้งสัดส่วนทับเอง",
    balance: "เฉลี่ยตามยอดเงินสดปัจจุบัน (ยังไม่มีประวัติพอ)",
    even: "เฉลี่ยเท่ากันทุกธนาคาร (ยังไม่มีข้อมูลพอ)",
};

/**
 * Cash & Liquidity — สามมุมมองในแท็บเดียว: ภาพรวมกลุ่ม (เดิม) / รายธนาคาร /
 * Treasury (แผนโอน + วงเงิน) ทั้งหมดอ่านจาก payload.cash ก้อนเดียวที่ engine
 * คำนวณไว้ครบแล้ว — ไม่มี orm.call เพิ่มยกเว้นปุ่ม "เสนอแผนโอน"
 */
export class BsfTabCash extends BsfTab {
    static template = "biz_smart_finance.TabCash";
    static components = { BsfAiCard };
    static props = { data: Object, unit: String, onReload: { type: Function, optional: true }, onSalesToCash: { type: Function, optional: true } };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ section: "group", bank: 0, suggesting: false });
    }

    get sections() {
        return [
            { id: "group", label: "ภาพรวมกลุ่ม", icon: "fa-line-chart" },
            { id: "bank", label: "รายธนาคาร", icon: "fa-bank" },
            { id: "treasury", label: "Treasury", icon: "fa-exchange" },
        ];
    }

    toggleSalesToCash(ev) {
        if (this.props.onSalesToCash) {
            this.props.onSalesToCash(ev.target.checked);
        }
    }

    setSection(id) {
        this.state.section = id;
    }

    get cash() {
        return this.props.data.cash;
    }

    get forecast() {
        return this.cash.forecast;
    }

    /** หนี้เกินกำหนดที่ยังไม่มีนัดรับเงิน — ไม่รวมใน collections leg ของกระแสเงินสด
     *  ต้องมีจุดแสดงผล ไม่งั้นยอดนี้หายไปจากทั้งกริดรายสัปดาห์และรายเดือนแบบเงียบ ๆ */
    get collectionReview() {
        const rows = this.cash.collection_review || [];
        const total = rows.reduce((sum, row) => sum + (row.amount || 0), 0);
        return { rows, total, count: rows.length };
    }

    get isManager() {
        return !!(this.props.data.ai && this.props.data.ai.is_manager);
    }

    get sharesBasisLabel() {
        return SHARES_BASIS_LABELS[this.cash.banks.shares_basis] || "";
    }

    // ---------------- กราฟ: กลุ่มรวม / เลือกดูรายธนาคาร ----------------
    get bankOptions() {
        return this.cash.banks.rows.filter((row) => row.bank_id);
    }

    onBankChange(ev) {
        this.state.bank = parseInt(ev.target.value, 10) || 0;
    }

    get selectedBankRow() {
        if (!this.state.bank) {
            return null;
        }
        return this.bankOptions.find((row) => row.bank_id === this.state.bank) || null;
    }

    get cashChart() {
        return this.memoChart(
            "cashChart",
            [this.forecast, this.cash, this.state.bank, this.unit],
            () => this._buildCashChart());
    }

    _buildCashChart() {
        const fc = this.forecast;
        const bankRow = this.selectedBankRow;
        if (bankRow) {
            return buildCashChart(
                fc.weeks.map((w) => w.label),
                bankRow.weeks.map((w) => this.scale(w.ending)),
                {
                    minCash: this.scale(bankRow.min_balance),
                    dividerIndex: 0, height: 294,
                    subs: fc.weeks.map((w) => w.sub),
                },
            );
        }
        return buildCashChart(
            fc.weeks.map((w) => w.label),
            fc.closing.map((v) => this.scale(v)),
            {
                minCash: this.scale(fc.min_cash),
                bufferCash: this.scale(this.cash.operating_buffer),
                dividerIndex: 0, height: 294,
                subs: fc.weeks.map((w) => w.sub),
            },
        );
    }

    // แถวของตารางสรุปรายสัปดาห์ (คอลัมน์ = สัปดาห์) — นิยามที่เดียว
    // drill: "ar"/"ap" = เซลล์กดเจาะดูใบครบกำหนดสัปดาห์นั้นได้
    get summaryRows() {
        return [
            { key: "opening", label: "Opening Cash", sign: 1, drill: "" },
            { key: "inflow_collections", label: "· Collections (เงินเข้าจากลูกหนี้/แผนบิล)", sign: 1, drill: "ar" },
            { key: "inflow_sales_to_cash", label: "· Sales to Cash (SO ยังไม่วางบิล)", sign: 1, drill: "" },
            { key: "inflow_other", label: "· Other Inflows (รายการกรอกมือ)", sign: 1, drill: "lines" },
            { key: "outflow_ap", label: "· AP & Payments (เจ้าหนี้/แผนจ่าย)", sign: -1, drill: "ap" },
            { key: "outflow_payroll_opex", label: "· Payroll & Opex", sign: -1, drill: "lines" },
            { key: "outflow_tax_other", label: "· Tax & Others", sign: -1, drill: "lines" },
            { key: "closing", label: "Closing Cash", sign: 1, drill: "" },
        ];
    }

    /** เซลล์รายสัปดาห์ → เอกสารครบกำหนดในสัปดาห์นั้น (สัปดาห์แรกรวมเกินกำหนด) */
    openWeekDrill(metric, row) {
        if (!metric.drill) {
            return;
        }
        if (metric.drill === "lines") {
            this.openForecastLines();
            return;
        }
        const week = this.forecast.weeks[row.index] || {};
        const dateFrom = row.index === 0 ? false : week.date_from;
        if (metric.drill === "ar") {
            this.openOpenMovesDue(
                `ลูกหนี้ครบกำหนด ${row.label}`, ["out_invoice"],
                dateFrom, week.date_to);
        } else {
            this.openOpenMovesDue(
                `เจ้าหนี้ครบกำหนด ${row.label}`, ["in_invoice"],
                dateFrom, week.date_to);
        }
    }

    openForecastLines() {
        this.openList("Cash Flow Lines", "biz.smart.finance.forecast.line", []);
    }

    // ---------------- มุมมองรายธนาคาร ----------------
    bankStatusColor(status) {
        if (status === "at_risk") {
            return LEVEL_COLORS.high;
        }
        if (status === "monitor") {
            return LEVEL_COLORS.medium;
        }
        return LEVEL_COLORS.low;
    }

    bankStatusLabel(status) {
        return BANK_STATUS_LABELS[status] || status;
    }

    /** วงเงินคงเหลือรวมของธนาคารนี้ (จากมุมมอง Treasury) — ไม่มีวงเงิน = 0 */
    /** วงเงินคงเหลือรวมต่อธนาคาร — สร้างแผนที่ครั้งเดียว ไม่ใช่ filter+reduce
     *  ทั้งลิสต์ใหม่ทุกแถวของตารางธนาคาร (O(ธนาคาร × วงเงิน) ต่อ render) */
    get availableLimitByBank() {
        return this.memoChart("availableLimitByBank", [this.cash], () => {
            const map = {};
            for (const row of this.cash.facilities.rows) {
                map[row.bank_id] = (map[row.bank_id] || 0) + row.available;
            }
            return map;
        });
    }

    bankAvailableLimit(bankId) {
        return this.availableLimitByBank[bankId] || 0;
    }

    /** ยอดปลายสัปดาห์ที่ 13 ของธนาคารนี้ (Forecast Closing W13) */
    bankForecastClosing(row) {
        const weeks = row.weeks || [];
        return weeks.length ? weeks[weeks.length - 1].ending : row.current_balance;
    }

    // ---------------- Treasury: แผนโอน ----------------
    purposeLabel(code) {
        return PURPOSE_LABELS[code] || code;
    }

    transferStateLabel(code) {
        return TRANSFER_STATE_LABELS[code] || code;
    }

    facilityStatusColor(status) {
        if (status === "risk") {
            return LEVEL_COLORS.high;
        }
        if (status === "monitor") {
            return LEVEL_COLORS.medium;
        }
        return LEVEL_COLORS.low;
    }

    facilityStatusLabel(status) {
        return FACILITY_STATUS_LABELS[status] || status;
    }

    /** ความยาวหลอด utilization (ตัดที่ 100% แต่คงสีเตือนถ้าเกิน) */
    barWidth(row) {
        const pct = row.utilisation_pct;
        if (pct === null || pct === undefined) {
            return 0;
        }
        return Math.max(0, Math.min(Number(pct), 100));
    }

    barColor(row) {
        return this.facilityStatusColor(row.status);
    }

    openTransfer(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "biz.smart.finance.bank.transfer",
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openNewTransfer() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "biz.smart.finance.bank.transfer",
            views: [[false, "form"]],
            target: "current",
        });
    }

    async suggestTransfers() {
        if (this.state.suggesting) {
            return;
        }
        this.state.suggesting = true;
        try {
            const result = await this.orm.call(
                "biz.smart.finance.dashboard", "action_bsf_suggest_transfers",
                [this.props.data.filters ? {
                    company_id: this.props.data.filters.company_id,
                    year: this.props.data.filters.year,
                    month: this.props.data.filters.month,
                    scenario: this.props.data.filters.scenario,
                } : {}]);
            this.notification.add(
                result.created
                    ? `เสนอแผนโอน ${result.created} รายการ`
                    : "ไม่มีธนาคารที่คาดว่าจะหลุด buffer ในช่วง 13 สัปดาห์",
                { type: result.created ? "success" : "info" });
            if (this.props.onReload) {
                this.props.onReload();
            }
        } catch (error) {
            this.notification.add("เสนอแผนโอนไม่สำเร็จ — ลองใหม่อีกครั้ง", { type: "danger" });
        } finally {
            this.state.suggesting = false;
        }
    }
}
