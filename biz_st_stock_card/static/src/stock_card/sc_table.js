/** @odoo-module **/

import { Component } from "@odoo/owl";
import { fmtMoney, fmtQty } from "@biz_st_stock_card/stock_card/sc_format";
import { headerGroups } from "@biz_st_stock_card/stock_card/sc_shared";

/**
 * ตารางสต๊อกการ์ดแบบลำดับชั้น
 *
 * server ส่ง lines มาเรียงพร้อมแสดงแล้ว component นี้แค่วาดตามลำดับ ไม่จัดเรียงเอง
 * และไม่คำนวณตัวเลขใหม่แม้แต่ช่องเดียว
 */
export class ScTable extends Component {
    static template = "biz_st_stock_card.ScTable";
    static props = {
        data: Object,
        onToggleFold: Function,
        onDrillDown: Function,
        onOpenProduct: Function,
    };

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
