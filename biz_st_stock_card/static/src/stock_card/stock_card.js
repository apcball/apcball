/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ScFilterBar } from "@biz_st_stock_card/stock_card/sc_filter_bar";
import { ScTable } from "@biz_st_stock_card/stock_card/sc_table";
import { fmtMoney, fmtQty } from "@biz_st_stock_card/stock_card/sc_format";

export class StockCard extends Component {
    static template = "biz_st_stock_card.StockCard";
    static components = { ScFilterBar, ScTable };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            // reloading = โหลดรอบต่อ ๆ ไป ตารางเดิมยังอยู่บนจอ การกางจึงไม่กะพริบ
            reloading: false,
            data: null,
            // ปล่อยให้ server เติมค่าตั้งต้น (ช่วงวันที่, เขตเวลา) — ไม่คำนวณซ้ำบน client
            options: this.props.action.context.sc_options || {},
        });
        onWillStart(() => this.load());
    }

    async load() {
        const first = !this.state.data;
        this.state.loading = true;
        this.state.reloading = !first;
        try {
            const data = await this.orm.call(
                "biz.stock.card.report", "get_report_data", [this.state.options]
            );
            this.state.data = data;
            // รับ options ที่ server normalize แล้วมาใช้แทนของเดิมทั้งดุ้น
            this.state.options = data.options;
        } finally {
            this.state.loading = false;
            this.state.reloading = false;
        }
    }

    async updateOptions(changes) {
        Object.assign(this.state.options, changes);
        await this.load();
    }

    async toggleFold(line) {
        const unfolded = (this.state.options.unfolded || []).slice();
        const index = unfolded.indexOf(line.id);
        if (line.unfolded) {
            if (index >= 0) {
                unfolded.splice(index, 1);
            }
            // แถวที่กางอยู่เพราะ unfold_level ต้องยุบได้ด้วย จึงลดระดับลงมาที่แถวนี้
            const level = line.level;
            if (level < this.state.options.unfold_level) {
                this.state.options.unfold_level = level;
            }
        } else if (index < 0) {
            unfolded.push(line.id);
        }
        await this.updateOptions({ unfolded });
    }

    async unfoldAll() {
        await this.updateOptions({ unfold_level: 7 });
    }

    async foldAll() {
        await this.updateOptions({ unfold_level: 1, unfolded: [] });
    }

    async drillDown(line, target) {
        const action = await this.orm.call(
            "biz.stock.card.report", "action_drill_down",
            [line.id, this.state.options, target]
        );
        this.actionService.doAction(action);
    }

    /** เปิดการ์ดสินค้ารายวันเป็นหน้าใหม่ — ชื่อ action คือข้อความบน breadcrumb */
    async openProductCard(line) {
        await this.actionService.doAction({
            type: "ir.actions.client",
            tag: "biz_st_stock_card.product_card",
            name: `รายละเอียดสินค้า: ${line.name}`,
            context: {
                sc_options: { ...this.state.options },
                sc_product_id: line.res_id,
                // ส่งสินค้าที่อยู่บนจออยู่แล้วไปเป็นตัวเลือกใน dropdown ของการ์ด
                // ไม่ต้องยิงคิวรีเพิ่ม และรายการที่เลือกได้ตรงกับรายงานที่กำลังดูเสมอ
                sc_products: this.productChoices,
            },
        });
    }

    get productChoices() {
        const seen = new Map();
        for (const line of (this.state.data && this.state.data.lines) || []) {
            if (line.group_type === "product" && line.res_id && !seen.has(line.res_id)) {
                seen.set(line.res_id, {
                    id: line.res_id,
                    name: line.code ? `${line.code} ${line.name}` : line.name,
                });
            }
        }
        return [...seen.values()];
    }

    async print(output) {
        const action = await this.orm.call(
            "biz.stock.card.wizard", "action_export_from_options",
            [this.state.options, output]
        );
        this.actionService.doAction(action);
    }

    get summary() {
        if (!this.state.data) {
            return [];
        }
        const totals = this.state.data.totals;
        const digits = this.state.data.company.qty_precision;
        const money = this.state.data.company.decimal_places;
        const showValue = this.state.data.options.show_value;
        const card = (label, qtyKey, valueKey, tone) => ({
            label,
            qty: fmtQty(totals[qtyKey], digits),
            value: showValue ? fmtMoney(totals[valueKey], money) : null,
            tone,
        });
        return [
            card("ยอดยกมา", "opening_qty", "opening_value", "neutral"),
            card("รับเข้า", "in_qty", "in_value", "in"),
            card("จ่ายออก", "out_qty", "out_value", "out"),
            card("คงเหลือ", "closing_qty", "closing_value", "close"),
        ];
    }

    get groupCount() {
        return this.state.data ? this.state.data.checks.group_count : 0;
    }
}

registry.category("actions").add("biz_st_stock_card.stock_card", StockCard);
