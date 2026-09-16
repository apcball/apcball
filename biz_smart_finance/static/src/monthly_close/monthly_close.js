/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { onMounted, useExternalListener, useState } from "@odoo/owl";
import { BsfTab } from "../dashboard/bsf_widgets";
import { BsfTabClose } from "../dashboard/tab_close";

// unit จำต่อเครื่องผ่าน localStorage — อ่าน/เขียนใน try/catch เสมอ
function readPref(key, fallback) {
    try {
        return window.localStorage.getItem(key) || fallback;
    } catch {
        return fallback;
    }
}

function writePref(key, value) {
    try {
        window.localStorage.setItem(key, value);
    } catch {
        // ignore — เป็นแค่ convenience
    }
}

/**
 * Monthly Close — client action ระดับเมนู (แยกออกจาก CFO Cockpit)
 * ใช้ component BsfTabClose เดิมเป็นเนื้อหา แต่ยิงเครื่องยนต์บาง
 * get_monthly_close_data ที่คืนเฉพาะสไลซ์ close (ไม่รันทั้ง 13 แท็บ)
 */
export class BsfMonthlyClose extends BsfTab {
    static template = "biz_smart_finance.MonthlyClose";
    static props = ["*"];
    static components = { BsfTabClose };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            error: "",
            data: null,
            companyId: "",
            year: "",
            // ผลต่าง TB เป็นยอดเล็ก — โหมดล้านบาทจะปัดหาย จึงเริ่มที่บาทเต็ม
            unit: readPref("bsf_unit", "thb"),
        });
        useExternalListener(window, "keydown", (ev) => {
            if (ev.key === "Escape" && this.zoomState.key) {
                this.closeZoom();
            }
        });
        // เหตุผลเดียวกับ CFO Cockpit — onWillStart resolve ก่อน render แรก
        // สปินเนอร์จึงไม่เคยขึ้นระหว่างที่ engine ทำงาน
        onMounted(() => this.load());
    }

    get unit() {
        return this.state.unit;
    }

    get rpcFilters() {
        return {
            company_id: this.state.companyId
                ? parseInt(this.state.companyId) : false,
            year: this.state.year ? parseInt(this.state.year) : false,
        };
    }

    async load() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const data = await this.orm.call(
                "biz.smart.finance.dashboard", "get_monthly_close_data",
                [this.rpcFilters]);
            this.state.data = data;
            this.state.companyId = data.filters.company_id
                ? String(data.filters.company_id) : "";
            this.state.year = String(data.filters.year);
        } catch (error) {
            this.state.error = (error.data && error.data.message) || String(error);
        } finally {
            this.state.loading = false;
        }
    }

    async setFilter(field, ev) {
        this.state[field] = ev.target.value;
        await this.load();
    }

    setUnit(unit) {
        this.state.unit = unit;
        writePref("bsf_unit", unit);
    }

    goBack() {
        this.env.config.historyBack();
    }
}

registry.category("actions").add(
    "biz_smart_finance.monthly_close", BsfMonthlyClose);
