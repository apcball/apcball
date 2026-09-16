/** @odoo-module **/

import { BsfTab, buildBarLine, buildStackedBar, FUNNEL_COLORS } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

const SOURCE_LABELS = {
    odoo: "ข้อมูลจาก Odoo",
    external: "ข้อมูลจากระบบภายนอก",
    mixed: "ผสม Odoo + ระบบภายนอก",
};

export class BsfTabInventory extends BsfTab {
    static template = "biz_smart_finance.TabInventory";
    static components = { BsfAiCard };

    get inv() {
        return this.props.data.inventory;
    }

    get sourceLabel() {
        return SOURCE_LABELS[this.inv.source] || this.inv.source;
    }

    /** แนวโน้มมูลค่าคงคลังรายงวด — แท่งปีนี้ + เส้นปีก่อน (scale ก่อนส่ง builder)
     *  ป้ายแกนใช้แค่ชื่อเดือน ("P1 · ม.ค. 2026" → "ม.ค.") — ป้ายเต็มยาวเกินไป
     *  จนซ้อนกันเมื่อมี 12 งวด ส่วนงวดเต็มยังอ่านได้จากหัวการ์ดและตาราง */
    get trendChart() {
        return this.memoChart("trendChart", [this.inv, this.unit], () =>
            this._buildTrendChart());
    }

    _buildTrendChart() {
        const trend = this.inv.trend;
        return buildBarLine(
            trend.map((p) => p.label.split(" ")[2] || p.label),
            trend.map((p) => this.scale(p.value)),
            [{
                key: "prior", label: "ปีก่อน", cls: "line_before",
                values: trend.map((p) => this.scale(p.value_prior || 0)),
            }],
            { height: 240 },
        );
    }

    get categoryBar() {
        return buildStackedBar(
            this.inv.by_category.map((c) => c.value), FUNNEL_COLORS,
        ).map((seg, index) => ({ ...seg, ...this.inv.by_category[index] }));
    }

    categoryColor(index) {
        return FUNNEL_COLORS[index % FUNNEL_COLORS.length];
    }

    /** null = คำนวณไม่ได้ (ไม่ใช่ศูนย์) */
    fmtTurn(value) {
        return value === null || value === undefined
            ? "—" : `${this.fmtNum(value, 2)}x`;
    }

    fmtDays(value) {
        return value === null || value === undefined
            ? "—" : `${this.fmtInt(value)} วัน`;
    }

    // ---------------- drill-downs ----------------
    openCategory(row) {
        if (row.categ_id) {
            this.openList(`สินค้า · ${row.name}`, "product.product", [
                ["categ_id", "child_of", row.categ_id],
            ]);
        }
    }

    openProduct(row) {
        this.openForm("product.product", row.product_id);
    }

    openGlItems() {
        const ids = this.inv.inventory_account_ids || [];
        if (ids.length) {
            this.openList("รายการบัญชีสินค้าคงเหลือ", "account.move.line", [
                ["account_id", "in", ids],
                ["parent_state", "=", "posted"],
                ["date", "<=", this.fyTo],
                ...this.companyDomain(),
            ]);
        }
    }

    openExtFacts() {
        this.openList("External Figures (สินค้าคงเหลือ)",
            "biz.smart.finance.ext.fact", [
                ["kind", "=", "inventory"],
                ...this.companyDomain(),
            ]);
    }
}
