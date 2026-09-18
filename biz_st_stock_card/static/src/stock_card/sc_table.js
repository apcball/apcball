/** @odoo-module **/

import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";
import { fmtMoney, fmtQty } from "@biz_st_stock_card/stock_card/sc_format";
import { headerGroups } from "@biz_st_stock_card/stock_card/sc_shared";

// ต้องใกล้เคียงความสูงจริงของแถว (ดู .sc-table td ใน stock_card.scss) — ใช้แค่คำนวณ
// หน้าต่างที่มองเห็น ความคลาดเคลื่อนเล็กน้อยจากแถวที่ตัวหนังสือยาวจนขึ้นบรรทัดใหม่
// ไม่กระทบตัวเลขรายงาน แค่ทำให้ spacer สูงคลาดจากจริงนิดหน่อย ซึ่ง overscan ชดเชยให้
const ROW_HEIGHT = 26;
const OVERSCAN = 15;
// รายงานที่กางแล้วไม่กี่ร้อยแถวไม่คุ้มที่จะยุ่งกับการคำนวณหน้าต่างเลย — คงพฤติกรรมเดิม
const VIRTUALIZE_THRESHOLD = 300;

/**
 * ตารางสต๊อกการ์ดแบบลำดับชั้น
 *
 * server ส่ง lines มาเรียงพร้อมแสดงแล้ว component นี้แค่วาดตามลำดับ ไม่จัดเรียงเอง
 * และไม่คำนวณตัวเลขใหม่แม้แต่ช่องเดียว
 *
 * เมื่อแถวเกิน ``VIRTUALIZE_THRESHOLD`` จะวาดเฉพาะแถวที่อยู่ในหรือใกล้ viewport
 * (ประมาณด้วยความสูงคงที่ + overscan) แทนการยัด DOM node ทุกแถวลงจอเดียว —
 * รายงานที่กางเต็มหลายพันแถวจะได้ไม่ทำให้เบราว์เซอร์ค้าง ตัวเลข/การจัดกลุ่มยังมาจาก
 * ``props.data.lines`` เส้นเดียวเหมือนเดิมทุกประการ แค่เลือกช่วงที่วาดเท่านั้น
 */
export class ScTable extends Component {
    static template = "biz_st_stock_card.ScTable";
    static props = {
        data: Object,
        onToggleFold: Function,
        onDrillDown: Function,
        onOpenProduct: Function,
    };

    setup() {
        this.wrapRef = useRef("wrap");
        this.vState = useState({ start: 0, end: VIRTUALIZE_THRESHOLD });
        this._onScroll = () => this._updateWindow();
        onMounted(() => {
            this.wrapRef.el.addEventListener("scroll", this._onScroll, { passive: true });
            this._updateWindow();
        });
        onPatched(() => this._updateWindow());
        onWillUnmount(() => {
            this.wrapRef.el.removeEventListener("scroll", this._onScroll);
        });
    }

    get virtualized() {
        return this.props.data.lines.length > VIRTUALIZE_THRESHOLD;
    }

    /** ช่วงแถวที่ควรวาด ณ ตำแหน่งเลื่อนปัจจุบัน — เผื่อ overscan ทั้งบนและล่าง */
    _updateWindow() {
        if (!this.virtualized || !this.wrapRef.el) {
            return;
        }
        const total = this.props.data.lines.length;
        const start = Math.max(
            0, Math.min(total, Math.floor(this.wrapRef.el.scrollTop / ROW_HEIGHT) - OVERSCAN)
        );
        const visibleCount = Math.ceil(this.wrapRef.el.clientHeight / ROW_HEIGHT) + OVERSCAN * 2;
        const end = Math.min(total, start + visibleCount);
        if (start !== this.vState.start || end !== this.vState.end) {
            this.vState.start = start;
            this.vState.end = end;
        }
    }

    get visibleLines() {
        if (!this.virtualized) {
            return this.props.data.lines;
        }
        return this.props.data.lines.slice(this.vState.start, this.vState.end);
    }

    get topSpacerHeight() {
        return this.virtualized ? this.vState.start * ROW_HEIGHT : 0;
    }

    get bottomSpacerHeight() {
        if (!this.virtualized) {
            return 0;
        }
        return Math.max(0, (this.props.data.lines.length - this.vState.end) * ROW_HEIGHT);
    }

    get showValue() {
        return this.props.data.options.show_value;
    }

    get hasDetail() {
        return this.props.data.lines.some(
            (line) => line.kind === "move" || line.kind === "more"
        );
    }

    /** ต้องตรงกับ ``biz.stock.card.report.report_columns()`` ฝั่ง Python */
    get columns() {
        const cols = [
            { key: "code", label: "รหัส / วันที่", type: "text" },
            { key: "name", label: "รายการ", type: "name" },
            { key: "uom_name", label: "หน่วย", type: "uom" },
        ];
        // ต้องตรงกับลำดับฝั่ง Python — ปรับมูลค่าอยู่ก่อนคงเหลือ เพื่อให้อ่านแถวเป็น
        // สมการได้ตรง ๆ: ยกมา + รับ − จ่าย + ปรับ = คงเหลือ
        const groups = [
            ["ยอดยกมา", "opening_qty", "opening_value"],
            ["รับ", "in_qty", "in_value"],
            ["จ่าย", "out_qty", "out_value"],
        ];
        for (const [group, qtyKey, valueKey] of groups) {
            cols.push({ key: qtyKey, group, label: "จำนวน", type: "qty" });
            if (this.showValue) {
                cols.push({ key: valueKey, group, label: "มูลค่า", type: "money" });
            }
        }
        if (this.showValue) {
            cols.push({ key: "adj_value", label: "ปรับมูลค่า", type: "money" });
        }
        cols.push({ key: "closing_qty", group: "คงเหลือ", label: "จำนวน", type: "qty" });
        if (this.showValue) {
            cols.push({ key: "closing_value", group: "คงเหลือ", label: "มูลค่า", type: "money" });
        }
        if (this.hasDetail) {
            cols.push({ key: "balance_qty", group: "คงเหลือสะสม", label: "จำนวน", type: "qty" });
            if (this.showValue) {
                cols.push({
                    key: "balance_value", group: "คงเหลือสะสม", label: "มูลค่า", type: "money",
                });
            }
        }
        return cols;
    }

    get headerGroups() {
        return headerGroups(this.columns);
    }

    rowClass(line) {
        const classes = ["sc-row", `sc-row-${line.kind}`, `sc-lv-${Math.min(line.level, 4)}`];
        if (line.flag === "negative") {
            classes.push("sc-row-negative");
        }
        if (line.kind === "group") {
            classes.push("sc-row-clickable");
        }
        return classes.join(" ");
    }

    cellValue(line, col) {
        if (col.type === "text") {
            return line.kind === "move" || line.kind === "more"
                ? line.date_display || ""
                : line.code || "";
        }
        if (col.type === "uom") {
            return line.uom_name || "";
        }
        const value = line[col.key];
        if (col.type === "qty") {
            return fmtQty(value, this.props.data.company.qty_precision);
        }
        if (col.type === "money") {
            return fmtMoney(value, this.props.data.company.decimal_places);
        }
        return value || "";
    }

    /** คอลัมน์คงเหลือสะสมมีความหมายกับแถวรายการเคลื่อนไหวเท่านั้น */
    isBlank(line, col) {
        if (col.key.startsWith("balance_")) {
            return line.kind !== "move" && line.kind !== "more";
        }
        return false;
    }

    indent(line) {
        return `padding-left:${8 + 18 * (line.level || 0)}px`;
    }

    onRowClick(line) {
        if (line.kind === "group" && line.res_id) {
            this.props.onDrillDown(line, "moves");
        } else if (line.kind === "move") {
            this.props.onDrillDown(line, "document");
        }
    }

    onCaretClick(line) {
        this.props.onToggleFold(line);
    }

    /** ชื่อสินค้าเป็นลิงก์เปิดการ์ดรายวัน — ส่วนอื่นของแถวยังเป็นการดูรายการเคลื่อนไหวเหมือนเดิม */
    isProductLink(line) {
        return line.kind === "group" && line.group_type === "product" && !!line.res_id;
    }

    onNameClick(line, ev) {
        if (!this.isProductLink(line)) {
            // ไม่ใช่แถวสินค้า — ปล่อยให้ event ไหลขึ้นไปที่แถวตามพฤติกรรมเดิม
            return;
        }
        ev.stopPropagation();
        this.props.onOpenProduct(line);
    }
}
