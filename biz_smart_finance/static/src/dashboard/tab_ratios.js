/** @odoo-module **/

import { BsfTab } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

const SOURCE_LABELS = {
    odoo: "ข้อมูลจาก Odoo (GL)",
    external: "ข้อมูลจากระบบภายนอก",
    mixed: "ผสม Odoo + ระบบภายนอก",
};

// อธิบายธงที่ engine ติดมากับแต่ละอัตราส่วน — ผู้ใช้ต้องรู้ว่าตัวเลขนี้ประมาณ
const FLAG_NOTES = {
    quick_approx: "ยังไม่ map บัญชีสินค้าคงเหลือ — Quick Ratio จึงเท่ากับ Current Ratio",
    de_approx: "ยังไม่ map บัญชีเงินกู้ — ใช้หนี้สินรวมแทนหนี้สินมีดอกเบี้ย",
    no_dio: "ยังไม่มีข้อมูลสินค้าคงเหลือ — CCC = DSO − DPO",
    partial: "บางบริษัทในกลุ่มยังไม่มีข้อมูลตัวตั้งของอัตราส่วนนี้",
    neg_base: "ตัวหารติดลบ (เช่น ส่วนของผู้ถือหุ้น/หนี้สินหมุนเวียนติดลบ) — "
        + "อัตราส่วนจะพลิกเครื่องหมายจนอ่านผิด จึงไม่แสดงตัวเลข",
};

// ratio ที่ "ยิ่งต่ำยิ่งดี" — ใช้ระบายสี delta ให้ถูกทาง
const LOWER_IS_BETTER = new Set([
    "debt_to_equity", "dio_days", "dso_days", "ccc_days",
]);

export class BsfTabRatios extends BsfTab {
    static template = "biz_smart_finance.TabRatios";
    static components = { BsfAiCard };

    get ra() {
        return this.props.data.ratios;
    }

    get sourceLabel() {
        return SOURCE_LABELS[this.ra.source] || this.ra.source;
    }

    /** ค่าตามหน่วย — null คือคำนวณไม่ได้ ต้องไม่แสดงเป็น 0 */
    fmtValue(value, unit) {
        if (value === null || value === undefined) {
            return "—";
        }
        if (unit === "pct") {
            return `${this.fmtNum(value, 1)}%`;
        }
        if (unit === "days") {
            return `${this.fmtInt(value)} วัน`;
        }
        return `${this.fmtNum(value, 2)}x`;
    }

    fmtDeltaUnit(value, unit) {
        if (value === null || value === undefined) {
            return "—";
        }
        const sign = Number(value) > 0 ? "+" : "";
        return `${sign}${this.fmtValue(value, unit)}`;
    }

    /** ทิศทางที่ดีต่างกันต่อ ratio — D/E ลดลงคือดี, ROE เพิ่มขึ้นคือดี */
    rowDeltaClass(row) {
        return this.deltaClass(row.delta, !LOWER_IS_BETTER.has(row.key));
    }

    flagNotes(row) {
        return (row.flags || [])
            .map((flag) => FLAG_NOTES[flag] || flag)
            .join(" · ");
    }

    // ---------------- drill-downs ----------------
    openExtFacts(companyId) {
        const domain = [["kind", "=", "ratio_input"]];
        if (companyId) {
            domain.push(["company_id", "=", companyId]);
        }
        this.openList("External Figures (ตัวเลขอัตราส่วน)",
            "biz.smart.finance.ext.fact", domain);
    }

    openConfig() {
        this.openList("Smart Finance Settings", "biz.smart.finance.config", []);
    }

    /** กดแถวเพื่อดูรายการบัญชีที่ประกอบเป็นตัวตั้งของอัตราส่วนนั้น */
    openRow(row) {
        if (this.ra.source === "external") {
            this.openExtFacts(false);
            return;
        }
        const drill = {
            current_ratio: ["asset_cash", "asset_receivable", "asset_current",
                "asset_prepayments"],
            quick_ratio: ["asset_cash", "asset_receivable", "asset_current",
                "asset_prepayments"],
            debt_to_equity: ["equity", "equity_unaffected"],
            gross_margin_pct: ["income", "income_other", "expense_direct_cost"],
            net_margin_pct: ["income", "income_other", "expense_direct_cost",
                "expense", "expense_depreciation"],
            roa_pct: ["income", "income_other", "expense_direct_cost",
                "expense", "expense_depreciation"],
            roe_pct: ["equity", "equity_unaffected"],
            dso_days: ["asset_receivable"],
            dpo_days: ["liability_payable"],
        }[row.key];
        if (drill) {
            const cumulative = !row.key.endsWith("_pct");
            this.openJournalItems(row.label, drill, cumulative);
        }
    }
}
