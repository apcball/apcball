/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { AgFilterBar } from "@biz_st_aging/stock_aging/ag_filter_bar";
import { AgTable } from "@biz_st_aging/stock_aging/ag_table";
import { fmtDays, fmtMoney, fmtPct, fmtQty } from "@biz_st_aging/stock_aging/ag_format";

export class StockAging extends Component {
    static template = "biz_st_aging.StockAging";
    static components = { AgFilterBar, AgTable };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({
            loading: true,
            // reloading = โหลดรอบต่อ ๆ ไป ตารางเดิมยังอยู่บนจอ การกางจึงไม่กะพริบ
            reloading: false,
            data: null,
            // ปล่อยให้ server เติมค่าตั้งต้น (ณ วันที่, เขตเวลา, config) — ไม่คำนวณซ้ำบน client
            options: this.props.action.context.ag_options || {},
        });
        onWillStart(() => this.load());
    }

    /**
     * @param {boolean} nocache ปุ่ม "ปรับปรุงข้อมูล" — ข้ามแคชระดับโหนดฝั่ง server
     *   (ปกติแคชหมดอายุเองเมื่อมีรายการใหม่ แต่ผู้ใช้กดแล้วต้องได้ของสดแน่ ๆ)
     */
    async load(nocache = false) {
        const first = !this.state.data;
        this.state.loading = true;
        this.state.reloading = !first;
        try {
            const payload = nocache === true
                ? { ...this.state.options, nocache: true }
                : this.state.options;
            const data = await this.orm.call(
                "biz.stock.aging.report", "get_report_data", [payload]
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
        // ถ้า server ปฏิเสธ (เช่น กางแล้วเกิน max_lines) ให้ options กลับไปค่าก่อนหน้า
        // ไม่งั้นทุกการโหลดถัดไปจะติดข้อผิดพลาดเดิมจนกว่าผู้ใช้จะเดาได้ว่าต้องหุบ
        const previous = { ...this.state.options };
        Object.assign(this.state.options, changes);
        try {
            await this.load();
        } catch (error) {
            this.state.options = previous;
            throw error;
        }
    }

    async resetFilters() {
        this.state.options = {};
        await this.load();
    }

    async toggleFold(line) {
        const unfolded = (this.state.options.unfolded || []).slice();
        const index = unfolded.indexOf(line.id);
        if (line.unfolded) {
            if (index >= 0) {
                unfolded.splice(index, 1);
            }
            if (line.level < this.state.options.unfold_level) {
                this.state.options.unfold_level = line.level;
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

    async drillDown(line) {
        const action = await this.orm.call(
            "biz.stock.aging.report", "action_drill_down", [line.id, this.state.options]
        );
        this.actionService.doAction(action);
    }

    async openProduct(line) {
        const action = await this.orm.call(
            "biz.stock.aging.report", "action_open_product", [line.id, this.state.options]
        );
        this.actionService.doAction(action);
    }

    async openConfig() {
        const action = await this.orm.call(
            "biz.stock.aging.report", "action_open_config", [this.state.options]
        );
        // ปิดไดอะล็อกตั้งค่าแล้วโหลดใหม่ — ขอบช่วง/เกณฑ์อาจเปลี่ยน
        this.actionService.doAction(action, { onClose: () => this.load() });
    }

    async print(output) {
        const action = await this.orm.call(
            "biz.stock.aging.wizard", "action_export_from_options",
            [this.state.options, output]
        );
        this.actionService.doAction(action);
    }

    // --- KPI cards ---------------------------------------------------
    get kpiCards() {
        if (!this.state.data) {
            return [];
        }
        const kpis = this.state.data.kpis;
        const showValue = this.state.data.options.show_value;
        const digits = this.state.data.company.qty_precision;
        const money = this.state.data.company.decimal_places;
        const symbol = this.state.data.company.currency_symbol;
        const cards = [
            {
                key: "value", tone: "primary", icon: "fa-cubes",
                label: showValue ? "มูลค่าสินค้าคงเหลือ" : "จำนวนสินค้าคงเหลือ",
                value: showValue ? `${symbol} ${fmtMoney(kpis.closing_value, money)}`
                                 : fmtQty(kpis.closing_qty, digits),
                sub: showValue ? `จำนวน ${fmtQty(kpis.closing_qty, digits)}` : "",
            },
            {
                key: "age", tone: "green", icon: "fa-calendar",
                label: "อายุเฉลี่ย",
                value: kpis.avg_age !== null ? `${fmtDays(kpis.avg_age)} วัน` : "-",
                sub: "",
            },
        ];
        const tones = ["red", "orange", "purple"];
        kpis.over.forEach((over, index) => {
            cards.push({
                key: `over${over.edge}`, tone: tones[index] || "red", icon: "fa-clock-o",
                label: `${showValue ? "มูลค่า" : "จำนวน"} > ${over.edge} วัน`,
                value: showValue ? `${symbol} ${fmtMoney(over.value, money)}`
                                 : fmtQty(over.qty, digits),
                sub: fmtPct(showValue ? over.pct_value : over.pct_qty),
            });
        });
        cards.push({
            key: "risk", tone: "blue", icon: "fa-bar-chart",
            label: "จำนวนรายการเสี่ยง",
            value: `${kpis.risk.count} รายการ`,
            sub: `(Non-Moving / Obsolete) จาก ${kpis.risk.product_count} สินค้า`,
        });
        return cards;
    }

    get groupCount() {
        return this.state.data ? this.state.data.checks.group_count : 0;
    }
}

registry.category("actions").add("biz_st_aging.stock_aging", StockAging);
