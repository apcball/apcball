/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ZOOM_STATE, ZoomMixin } from "./bsf_widgets";

/**
 * การ์ด "AI CFO Brief" ใช้ซ้ำบนทุกแท็บ — ส่งแค่ชื่อแท็บ + filters ไป
 * engine ฝั่ง server เป็นคนดึงตัวเลขเอง (client ไม่เคยส่งตัวเลข)
 */
export class BsfAiCard extends Component {
    static template = "biz_smart_finance.AiCard";
    static props = { tab: String, data: Object };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ loading: false, brief: null });
        this.zoomState = useState(ZOOM_STATE);
    }

    get configured() {
        return !!(this.props.data.ai && this.props.data.ai.configured);
    }

    get filters() {
        const f = this.props.data.filters;
        return {
            company_id: f.company_id,
            year: f.year,
            month: f.month,
            scenario: f.scenario,
            // แท็บ Compare สร้างคอลัมน์จากสองคีย์นี้ — ถ้าไม่ส่งไปด้วย engine
            // จะ re-run แบบปิดการเปรียบเทียบ แล้ว brief ได้ payload ว่าง
            compare_mode: f.compare_mode || false,
            compare_count: f.compare_count || false,
        };
    }

    get sortedActions() {
        if (!this.state.brief) {
            return [];
        }
        return [...this.state.brief.actions].sort(
            (a, b) => a.priority - b.priority);
    }

    async generate() {
        if (this.state.loading) {
            return;
        }
        this.state.loading = true;
        try {
            this.state.brief = await this.orm.call(
                "biz.smart.finance.ai", "generate_brief",
                [this.props.tab, this.filters]);
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || String(error),
                { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}

Object.assign(BsfAiCard.prototype, ZoomMixin);
