/** @odoo-module **/

import { Component } from "@odoo/owl";
import { fmtDays, fmtMoney, fmtMonths, fmtQty } from "@biz_st_aging/stock_aging/ag_format";
import { headerTiers } from "@biz_st_aging/stock_aging/ag_shared";

/**
 * ตารางอายุสินค้าคงเหลือแบบลำดับชั้น
 *
 * server ส่ง lines และสเปกคอลัมน์ (data.columns) มาพร้อมแสดงแล้ว component นี้แค่วาดตามลำดับ
 * ไม่จัดเรียงเอง และไม่คำนวณตัวเลขใหม่แม้แต่ช่องเดียว
 */
export class AgTable extends Component {
    static template = "biz_st_aging.AgTable";
    static props = {
        data: Object,
        onToggleFold: Function,
        onDrillDown: Function,
        onOpenProduct: Function,
    };

    get columns() {
        return this.props.data.columns;
    }

    get tiers() {
        return headerTiers(this.columns);
    }

    rowClass(line) {
        const classes = ["ag-row", `ag-row-${line.kind}`, `ag-lv-${Math.min(line.level, 4)}`];
        if (line.flag === "negative") {
            classes.push("ag-row-negative");
        }
        if (line.kind === "group") {
            classes.push("ag-row-clickable");
        }
        return classes.join(" ");
    }

    cellClass(col) {
        const classes = ["ag-cell-num"];
        if (col.bucket) {
            classes.push(`ag-cell-${col.bucket}`);
        }
        return classes.join(" ");
    }

    /** ค่าที่ไม่มีความหมายกับแถวนี้ (ตัวชี้วัดของแถวเหนือระดับสินค้า) แสดงเป็นขีดกลาง */
    cellValue(line, col) {
        const value = line[col.key];
        const company = this.props.data.company;
        switch (col.type) {
            case "text":
                return line.code || "";
            case "uom":
                return line.uom_name || "";
            case "qty":
                return fmtQty(value, company.qty_precision);
            case "money":
                return fmtMoney(value, company.decimal_places);
            case "days":
                return fmtDays(value);
            case "months":
                return fmtMonths(value);
            default:
                return value || "";
        }
    }

    statusLabel(value) {
        return this.props.data.status_labels[value] || value || "-";
    }

    totalValue(col) {
        const totals = this.props.data.totals;
        if (col.type === "name") {
            return totals.name;
        }
        if (col.type === "status" || col.type === "text" || col.type === "uom") {
            return "";
        }
        if (!col.additive && col.key !== "avg_age") {
            return "-";
        }
        return this.cellValue(totals, col);
    }

    indent(line) {
        return `padding-left:${8 + 18 * (line.level || 0)}px`;
    }

    onRowClick(line) {
        if (line.kind === "group" && line.res_id) {
            this.props.onDrillDown(line);
        }
    }

    onCaretClick(line) {
        this.props.onToggleFold(line);
    }

    isProductLink(line) {
        return line.kind === "group" && line.group_type === "product" && !!line.res_id;
    }

    onNameClick(line, ev) {
        if (!this.isProductLink(line)) {
            return;
        }
        ev.stopPropagation();
        this.props.onOpenProduct(line);
    }
}
