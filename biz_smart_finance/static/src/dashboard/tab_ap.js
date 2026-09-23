/** @odoo-module **/

import { AGING_COLORS, BsfTab, buildBarLine, buildStackedBar } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

export class BsfTabAp extends BsfTab {
    static template = "biz_smart_finance.TabAp";
    static components = { BsfAiCard };

    get ap() {
        return this.props.data.ap;
    }

    get forecast() {
        return this.props.data.cash.forecast;
    }

    get agingBuckets() {
        const aging = this.ap.aging;
        return [
            { code: "current", label: "Current", amount: aging.current },
            { code: "b1_30", label: "1 - 30 days", amount: aging.b1_30 },
            { code: "b31_60", label: "31 - 60 days", amount: aging.b31_60 },
            { code: "b60_plus", label: "> 60 days", amount: aging.b60_plus },
        ];
    }

    get agingBar() {
        return buildStackedBar(
            this.agingBuckets.map((b) => b.amount), AGING_COLORS,
        ).map((seg, index) => ({ ...seg, ...this.agingBuckets[index] }));
    }

    get planChart() {
        return this.memoChart("planChart", [this.forecast, this.unit], () =>
            this._buildPlanChart());
    }

    _buildPlanChart() {
        const fc = this.forecast;
        return buildBarLine(
            fc.weeks.map((w) => w.label),
            fc.planned_ap.map((v) => this.scale(v)),
            [
                { key: "before", label: "Cash Availability", cls: "line_before",
                  values: fc.before_ap.map((v) => this.scale(v)) },
                { key: "after", label: "Cash After Payments", cls: "line_forecast",
                  values: fc.closing.map((v) => this.scale(v)) },
            ],
            {
                minCash: this.scale(fc.min_cash), height: 264,
                subs: fc.weeks.map((w) => w.sub),
            },
        );
    }

    bucketColor(index) {
        return AGING_COLORS[index % AGING_COLORS.length];
    }

    openSupplier(row) {
        if (row.partner_id) {
            this.openList(row.name, "account.move", [
                ["move_type", "in", ["in_invoice", "in_refund"]],
                ["state", "=", "posted"],
                ["payment_state", "in", ["not_paid", "partial"]],
                ["partner_id", "=", row.partner_id],
            ]);
        }
    }

    openOverdueBills() {
        this.openList("บิลค้างจ่ายเกินกำหนด", "account.move", [
            ["move_type", "in", ["in_invoice", "in_refund"]],
            ["state", "=", "posted"],
            ["payment_state", "in", ["not_paid", "partial"]],
        ]);
    }

    openOpenPos() {
        this.openList("PO วัสดุคงค้าง", "purchase.order", [
            ["state", "in", ["purchase", "done"]],
            ["invoice_status", "!=", "invoiced"],
            ...this.companyDomain(),
        ]);
    }

    // ---------------- drill-downs ----------------
    /** ช่องปฏิทินจ่าย: approved = บิลตั้งแล้วครบกำหนดสัปดาห์นั้น */
    openCalendarApproved(week) {
        const full = this.forecast.weeks[week.index] || {};
        this.openOpenMovesDue(
            `บิลครบกำหนด ${week.label}`, ["in_invoice"],
            week.index === 0 ? false : full.date_from, full.date_to);
    }

    /** pending = งวดแผนจ่ายผู้รับเหมาที่ due ในสัปดาห์นั้น */
    openCalendarPending(week) {
        const full = this.forecast.weeks[week.index] || {};
        this.openList(
            `แผนจ่ายผู้รับเหมา ${week.label}`, "ai.pm.vendor.payment.line", [
                ["due_date", ">=", full.date_from],
                ["due_date", "<=", full.date_to],
                ...this.companyDomain("project_id.company_id"),
            ]);
    }

    /** ถัง aging → บิลค้างชำระในช่วงอายุนั้น (นับจากวันนี้) */
    openAgingBucket(seg) {
        const today = this.echoFilters.today;
        const ranges = {
            current: [today, false],
            b1_30: [this.dateOffset(today, -30), this.dateOffset(today, -1)],
            b31_60: [this.dateOffset(today, -60), this.dateOffset(today, -31)],
            b60_plus: [false, this.dateOffset(today, -61)],
        };
        const range = ranges[seg.code] || [false, false];
        this.openOpenMovesDue(
            `เจ้าหนี้ค้างจ่าย · ${seg.label}`, ["in_invoice"],
            range[0], range[1]);
    }

    /** ถัง committed PO → PO ที่นัดรับของในช่วงนั้น */
    openCommittedBucket(code, label) {
        const today = this.echoFilters.today;
        const ranges = {
            b30: [false, this.dateOffset(today, 30)],
            b31_60: [this.dateOffset(today, 31), this.dateOffset(today, 60)],
            b61_90: [this.dateOffset(today, 61), this.dateOffset(today, 90)],
            b90_plus: [this.dateOffset(today, 91), false],
        };
        const range = ranges[code] || [false, false];
        const domain = [
            ["state", "in", ["purchase", "done"]],
            ["invoice_status", "!=", "invoiced"],
            ...this.companyDomain(),
        ];
        if (range[0]) {
            domain.push(["date_planned", ">=", range[0]]);
        }
        if (range[1]) {
            domain.push(["date_planned", "<=", `${range[1]} 23:59:59`]);
        }
        this.openList(`PO วัสดุ · ${label}`, "purchase.order", domain);
    }
}
