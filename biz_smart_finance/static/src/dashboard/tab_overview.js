/** @odoo-module **/

import { BsfTab, buildCashChart } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

export class BsfTabOverview extends BsfTab {
    static template = "biz_smart_finance.TabOverview";
    static components = { BsfAiCard };
    static props = { data: Object, unit: String, onTab: Function };

    get ov() {
        return this.props.data.overview;
    }

    get forecast() {
        return this.props.data.cash.forecast;
    }

    get cashChart() {
        return this.memoChart("cashChart", [this.forecast, this.unit], () => {
            const fc = this.forecast;
            return buildCashChart(
                fc.weeks.map((w) => w.label),
                fc.closing.map((v) => this.scale(v)),
                {
                    minCash: this.scale(fc.min_cash), dividerIndex: 0,
                    // A wider viewBox prevents SVG text from scaling up on an
                    // executive widescreen; the Y gutter keeps negative cash
                    // labels intact instead of clipping them at the edge.
                    width: 1200, padX: 92, height: 178,
                    subs: fc.weeks.map((w) => w.sub),
                },
            );
        });
    }

    get cashBi() {
        const fc = this.forecast;
        const alerts = fc.alerts || [];
        return {
            opening: fc.opening || 0,
            minimum: fc.closing && fc.closing.length ? Math.min(...fc.closing) : 0,
            firstBreach: alerts.length ? alerts[0].label : "ไม่มี",
            gap: alerts.length ? alerts[0].gap : 0,
            alert: alerts.length > 0,
        };
    }

    // ---------------- dimension control board ----------------
    jump(tab) {
        this.props.onTab(tab);
    }

    dimValue(dim) {
        if (dim.value === null || dim.value === undefined) {
            return "—";
        }
        switch (dim.fmt) {
            case "money": return this.fmtMoney(dim.value);
            case "pct":   return this.fmtPct(dim.value);
            case "x":     return this.fmtNum(dim.value, 2) + "x";
            case "days":  return this.fmtInt(dim.value) + " วัน";
            default:      return this.fmtInt(dim.value);
        }
    }

    openDimRisk(risk) {
        if (risk.source === "register" && risk.id) {
            this.openForm("biz.smart.finance.risk", risk.id);
        } else {
            this.jump("risk");
        }
    }

    // ---------------- KPI drill-downs ----------------
    openRevenue() {
        this.openMoves("รายได้ YTD — ใบแจ้งหนี้ที่ลงบัญชี",
            ["out_invoice", "out_refund"]);
    }

    openPnl() {
        this.openJournalItems("รายการงบกำไรขาดทุน YTD", [
            "income", "income_other", "expense",
            "expense_depreciation", "expense_direct_cost",
        ]);
    }

    openCash() {
        this.openJournalItems(
            "รายการบัญชีเงินสด/ธนาคาร", ["asset_cash"], true);
    }

    openConfig() {
        this.openList("Smart Finance Settings",
            "biz.smart.finance.config", []);
    }

    openBacklog(row) {
        this.openList(
            `Backlog · ${row.name}`, "sale.order",
            [["state", "=", "sale"], ["company_id", "=", row.company_id],
             ["invoice_status", "in", ["to invoice", "no"]]],
        );
    }
}
