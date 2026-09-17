/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { fmtMoney, fmtQty } from "@biz_st_stock_card/stock_card/sc_format";
import { DATE_PRESETS, headerGroups, presetRange } from "@biz_st_stock_card/stock_card/sc_shared";

/**
 * การ์ดสินค้ารายวัน
 *
 * เปิดจากปุ่ม "รายละเอียด" ที่แถวสินค้าของสต๊อกการ์ด แล้วอ่านสินค้าตัวนั้นเป็นไทม์ไลน์
 * รายวัน — รับเข้า / จ่ายออก / เปลี่ยนแปลง / คงเหลือสะสม พร้อมราคาต่อหน่วยของวันนั้น
 *
 * component นี้ **ไม่คำนวณตัวเลขใหม่แม้แต่ช่องเดียว** เหมือน ScTable — server ส่ง
 * แถวที่พร้อมวาดมาแล้ว หน้าที่ของที่นี่คือจัดวางและจัดรูปแบบตัวเลขเท่านั้น
 */
export class ProductCard extends Component {
    static template = "biz_st_stock_card.ProductCard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        const context = this.props.action.context || {};
        this.presets = DATE_PRESETS;
        this.state = useState({
            loading: true,
            reloading: false,
            data: null,
            // ปล่อยให้ server เติมค่าตั้งต้นและ normalize เหมือนหน้ารายงานหลัก
            options: context.sc_options || {},
            productId: context.sc_product_id || false,
            products: context.sc_products || [],
        });
        onWillStart(() => this.load());
    }

    async load() {
        const first = !this.state.data;
        this.state.loading = true;
        this.state.reloading = !first;
        try {
            const data = await this.orm.call(
                "biz.stock.card.report", "get_product_card",
                [this.state.options, this.state.productId]
            );
            this.state.data = data;
            this.state.options = data.options;
            this.state.productId = data.product.id;
            // สินค้าที่กำลังดูต้องมีอยู่ในรายการเสมอ ไม่งั้น dropdown จะโชว์ชื่อสินค้าอื่น
            // ทั้งที่ตารางเป็นของสินค้าตัวนี้ (เช่นเปิดหน้านี้ตรง ๆ โดยไม่ผ่านรายงาน)
            if (!this.state.products.some((p) => p.id === data.product.id)) {
                this.state.products = [
                    { id: data.product.id, name: data.product.display_name },
                    ...this.state.products,
                ];
            }
        } finally {
            this.state.loading = false;
            this.state.reloading = false;
        }
    }

    async updateOptions(changes) {
        Object.assign(this.state.options, changes);
        await this.load();
    }

    onDateChange(field, ev) {
        if (ev.target.value) {
            this.updateOptions({ [field]: ev.target.value });
        }
    }

    applyPreset(presetId) {
        this.updateOptions(presetRange(presetId));
    }

    async onProductChange(ev) {
        this.state.productId = parseInt(ev.target.value, 10);
        await this.load();
    }

    /** ย้อนกลับไปจอก่อนหน้าใน breadcrumb (สต๊อกการ์ดที่เปิดการ์ดนี้มา) */
    goBack() {
        const config = this.env.config;
        if (config && config.historyBack) {
            config.historyBack();
        } else {
            // เปิดหน้านี้ตรง ๆ โดยไม่มีจอก่อนหน้าใน stack — ถอยด้วยประวัติของเบราว์เซอร์แทน
            window.history.back();
        }
    }

    /** get_formview_action ใส่ views มาให้ครบแล้ว จึงไม่ตกกับดัก _preprocessAction ของ OWL */
    async openProductForm() {
        const action = await this.orm.call(
            "product.product", "get_formview_action", [[this.state.productId]]
        );
        await this.actionService.doAction(action);
    }

    /** กดแถววัน → ดูบรรทัดเคลื่อนไหวจริงของวันนั้น (domain สร้างที่เซิร์ฟเวอร์) */
    async openDay(row) {
        if (!row.move_count) {
            return;
        }
        const action = await this.orm.call(
            "biz.stock.card.report", "action_day_moves",
            [this.state.options, this.state.productId, row.date]
        );
        await this.actionService.doAction(action);
    }

    get showValue() {
        return this.state.data && this.state.data.options.show_value;
    }

    get summary() {
        if (!this.state.data) {
            return [];
        }
        const totals = this.state.data.totals;
        const digits = this.state.data.company.qty_precision;
        const money = this.state.data.company.decimal_places;
        const card = (label, qtyKey, valueKey, tone) => ({
            label,
            qty: fmtQty(totals[qtyKey], digits),
            value: this.showValue ? fmtMoney(totals[valueKey], money) : null,
            tone,
        });
        return [
            card("ยอดยกมา", "opening_qty", "opening_value", "neutral"),
            card("รับเข้า", "in_qty", "in_value", "in"),
            card("จ่ายออก", "out_qty", "out_value", "out"),
            card("คงเหลือ", "closing_qty", "closing_value", "close"),
        ];
    }

    get avgCost() {
        const cost = this.state.data && this.state.data.product.avg_cost;
        return cost === null || cost === undefined
            ? null
            : fmtMoney(cost, this.state.data.company.decimal_places);
    }

    /** ต้องตรงกับสิ่งที่ ``get_product_card`` ส่งมาในแต่ละแถววัน */
    get columns() {
        const value = this.showValue;
        const cols = [{ key: "label", label: "วันที่", type: "text" }];
        cols.push({ key: "in_qty", group: "รับเข้า", label: "จำนวน", type: "qty" });
        if (value) {
            cols.push({ key: "unit_in", group: "รับเข้า", label: "ราคา/หน่วย", type: "money" });
            cols.push({ key: "in_value", group: "รับเข้า", label: "มูลค่า", type: "money" });
        }
        cols.push({ key: "out_qty", group: "จ่ายออก", label: "จำนวน", type: "qty" });
        if (value) {
            cols.push({ key: "unit_out", group: "จ่ายออก", label: "ราคา/หน่วย", type: "money" });
            cols.push({ key: "out_value", group: "จ่ายออก", label: "มูลค่า", type: "money" });
        }
        if (value && this.hasAdjustment) {
            cols.push({ key: "adj_value", label: "ปรับมูลค่า", type: "money" });
        }
        cols.push({ key: "change", label: "เปลี่ยนแปลง", type: "change" });
        cols.push({ key: "balance_qty", group: "คงเหลือ", label: "จำนวน", type: "qty" });
        if (value) {
            cols.push({ key: "balance_value", group: "คงเหลือ", label: "มูลค่า", type: "money" });
        }
        return cols;
    }

    get hasAdjustment() {
        return (this.state.data.days || []).some((row) => row.adj_value);
    }

    get headerGroups() {
        return headerGroups(this.columns);
    }

    /** แถวยอดยกมาที่ปักหัวตาราง — ถือเฉพาะยอดคงเหลือ ไม่มีการเคลื่อนไหวของตัวเอง */
    get openingRow() {
        const totals = this.state.data.totals;
        return {
            kind: "opening",
            label: "ยอดยกมา",
            move_count: 0,
            balance_qty: totals.opening_qty,
            balance_value: totals.opening_value,
        };
    }

    get totalRow() {
        const totals = this.state.data.totals;
        return {
            kind: "total",
            label: totals.name,
            move_count: 0,
            in_qty: totals.in_qty,
            in_value: totals.in_value,
            out_qty: totals.out_qty,
            out_value: totals.out_value,
            adj_value: totals.adj_value,
            change: totals.change,
            balance_qty: totals.closing_qty,
            balance_value: totals.closing_value,
        };
    }

    rowClass(row) {
        const classes = ["sc-row", `sc-card-row-${row.kind || "day"}`];
        if (row.in_qty) {
            classes.push("sc-card-row-in");
        }
        if (row.out_qty) {
            classes.push("sc-card-row-out");
        }
        if (row.flag === "negative") {
            classes.push("sc-row-negative");
        }
        if (row.move_count) {
            classes.push("sc-row-clickable");
        }
        return classes.join(" ");
    }

    /** ช่องที่ไม่มีความหมายกับแถวนั้นต้องว่าง ไม่ใช่ศูนย์หรือขีดกลาง */
    isBlank(row, col) {
        if (row.kind === "opening") {
            return !col.key.startsWith("balance_");
        }
        // ราคาต่อหน่วยของ "ทั้งงวด" ไม่มีอยู่จริง — ต้นทุนเฉลี่ยอยู่ที่การ์ดด้านบนแล้ว
        return row.kind === "total" && col.key.startsWith("unit_");
    }

    cellValue(row, col) {
        if (col.type === "text") {
            return row.label || row.date_display || "";
        }
        const value = row[col.key];
        if (col.type === "qty") {
            return fmtQty(value, this.state.data.company.qty_precision);
        }
        return fmtMoney(value, this.state.data.company.decimal_places);
    }

    changeValue(row) {
        return fmtQty(Math.abs(row.change || 0), this.state.data.company.qty_precision);
    }
}

registry.category("actions").add("biz_st_stock_card.product_card", ProductCard);
