/** @odoo-module **/

import { useSetupAction } from "@web/webclient/actions/action_hook";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { onMounted, useExternalListener, useState } from "@odoo/owl";
import { BsfTab, MONTH_NAMES } from "./bsf_widgets";
import { BsfTabOverview } from "./tab_overview";
import { BsfTabStatements } from "./tab_statements";
import { BsfTabControlling } from "./tab_controlling";
import { BsfTabCash } from "./tab_cash";
import { BsfTabForecast } from "./tab_forecast";
import { BsfTabSales } from "./tab_sales";
import { BsfTabChannel } from "./tab_channel";
import { BsfTabMargin } from "./tab_margin";
import { BsfTabAp } from "./tab_ap";
import { BsfTabInventory } from "./tab_inventory";
import { BsfTabRatios } from "./tab_ratios";
import { BsfTabCompare } from "./tab_compare";
import { BsfTabRisk } from "./tab_risk";
import { BsfTabStrategy } from "./tab_strategy";
import { BsfTabAi } from "./tab_ai";

// theme/unit จำต่อเครื่องผ่าน localStorage — อ่าน/เขียนใน try/catch เสมอ
// (โหมด private หรือ browser ที่บล็อก storage จะ throw ตั้งแต่ accessor)
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
        // ignore — ความจำเป็นแค่ convenience
    }
}

/**
 * CFO Cockpit — root component
 * เต็มความสูงเสมอ: header / toolbar / tab strip อยู่กับที่ มีเฉพาะ
 * .o_bsf_body ที่ scroll  ทุกแท็บรับ payload ทั้งก้อน + unit ปัจจุบัน
 */
export class BsfDashboard extends BsfTab {
    static template = "biz_smart_finance.Dashboard";
    static props = ["*"];
    static components = {
        BsfTabOverview, BsfTabStatements, BsfTabRatios, BsfTabCompare,
        BsfTabControlling, BsfTabCash, BsfTabForecast, BsfTabSales,
        BsfTabChannel, BsfTabMargin, BsfTabAp,
        BsfTabInventory, BsfTabRisk, BsfTabAi, BsfTabStrategy,
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            error: "",
            exporting: "",
            data: null,
            companyId: "",
            year: "",
            month: "",
            scenario: "base",
            includeSalesToCash: false,
            planId: "",
            // แท็บ Sales Channel — โหลดสไลซ์ของตัวเองตอนเปิดครั้งแรก
            channelDim: "partner",
            channelId: "",
            // แท็บ Compare — ว่าง = ยังไม่เปิด (engine ไม่ยิงคิวรีเพิ่ม)
            compareMode: "",
            compareCount: "4",
            unit: readPref("bsf_unit", "mb"),
            // SAP Fiori เป็นธีมสว่าง จึงเป็นค่าตั้งต้น (Morning Horizon)
            // ผู้ใช้เดิมที่เคยสลับไว้ยังได้ค่าที่ตัวเองเลือกจาก localStorage
            theme: readPref("bsf_theme", "light"),
            hintsOpen: readPref("bsf_hints", "0") === "1",
            tab: "overview",
            menuGroup: "overview",
        });
        // Odoo restores this snapshot when returning through the action stack.
        // Keep selections only: refresh data and permissions on every return.
        const saved = this.props.state?.dashboard;
        if (saved) {
            Object.assign(this.state, saved.selections);
        }
        useSetupAction({ getLocalState: () => ({ dashboard: this.getActionState() }) });
        // Esc = หุบกล่องที่กางอยู่ (ปุ่มบนการ์ดกับพื้นหลังก็ปิดได้เหมือนกัน)
        useExternalListener(window, "keydown", (ev) => {
            if (ev.key === "Escape" && this.zoomState.key) {
                this.closeZoom();
            }
        });
        // โหลดหลัง mount ไม่ใช่ onWillStart — onWillStart resolve **ก่อน**
        // render แรก state.loading จึงเป็น false ตั้งแต่เฟรมแรกเสมอ และบล็อก
        // สปินเนอร์ในเทมเพลตไม่เคยถูกแสดง ผู้ใช้เห็นจอว่างตลอดเวลาที่ engine ทำงาน
        onMounted(() => this.load());
    }

    getActionState() {
        // Detach reactive objects so later edits cannot mutate action history.
        return JSON.parse(JSON.stringify({
            selections: {
                companyId: this.state.companyId,
                year: this.state.year,
                month: this.state.month,
                scenario: this.state.scenario,
                includeSalesToCash: this.state.includeSalesToCash,
                planId: this.state.planId,
                channelDim: this.state.channelDim,
                channelId: this.state.channelId,
                compareMode: this.state.compareMode,
                compareCount: this.state.compareCount,
                unit: this.state.unit,
                theme: this.state.theme,
                hintsOpen: this.state.hintsOpen,
                tab: this.state.tab,
                menuGroup: this.state.menuGroup,
            },
        }));
    }

    get unit() {
        return this.state.unit;
    }

    get rpcFilters() {
        return {
            company_id: this.state.companyId
                ? parseInt(this.state.companyId) : false,
            year: this.state.year ? parseInt(this.state.year) : false,
            month: this.state.month ? parseInt(this.state.month) : false,
            scenario: this.state.scenario,
            include_sales_to_cash: this.state.includeSalesToCash,
            plan_id: this.state.planId ? parseInt(this.state.planId) : false,
            channel_dim: this.state.channelDim || "partner",
            channel_id: this.state.channelId
                ? parseInt(this.state.channelId) : 0,
            compare_mode: this.state.compareMode || false,
            compare_count: parseInt(this.state.compareCount) || 4,
        };
    }

    async load() {
        const requestId = this._loadRequestId = (this._loadRequestId || 0) + 1;
        this.state.loading = true;
        this.state.error = "";
        try {
            const data = await this.orm.call(
                "biz.smart.finance.dashboard", "get_dashboard_data",
                [this.rpcFilters]);
            if (requestId !== this._loadRequestId) {
                return;
            }
            if (this.state.tab === "channel") {
                const channel = await this.orm.call(
                    "biz.smart.finance.dashboard", "get_channel_data", [data.filters]);
                if (requestId !== this._loadRequestId) {
                    return;
                }
                data.channel = channel.channel;
            }
            this.state.data = data;
            this.applyFilters(data.filters);
        } catch (error) {
            if (requestId === this._loadRequestId) {
                this.state.error = (error.data && error.data.message) || String(error);
            }
        } finally {
            if (requestId === this._loadRequestId) {
                this.state.loading = false;
            }
        }
    }

    applyFilters(filters) {
        this.state.companyId = filters.company_id
            ? String(filters.company_id) : "";
        this.state.year = String(filters.year);
        this.state.month = String(filters.month);
        this.state.scenario = filters.scenario;
        this.state.includeSalesToCash = Boolean(filters.include_sales_to_cash);
        this.state.planId = filters.plan_id
            ? String(filters.plan_id) : "";
        this.state.compareMode = filters.compare_mode || "";
        this.state.compareCount = String(filters.compare_count || 4);
        this.state.channelDim = filters.channel_dim || "partner";
        this.state.channelId = filters.channel_id
            ? String(filters.channel_id) : "";
    }

    async setFilter(field, ev) {
        this.state[field] = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
        await this.load();
    }

    async setSalesToCash(enabled) {
        this.state.includeSalesToCash = Boolean(enabled);
        await this.load();
    }

    /**
     * โหลดสไลซ์เดียวแล้วปะทับลง payload เดิม — ใช้กับตัวกรองที่กระทบแท็บเดียว
     * (ช่องทางขาย) การเรียก get_dashboard_data ใหม่หมาย
     * ถึงสร้างครบ 13 แท็บเพื่อรีเฟรชตารางเดียว
     */
    async loadSlice(method, key) {
        // A slice cannot complete a pending full refresh or repair a failed one.
        // Rebuild all tabs so they always describe the same filter selection.
        if (this.state.loading || this.state.error || !this.state.data) {
            return this.load();
        }
        const requestId = this._loadRequestId = (this._loadRequestId || 0) + 1;
        this.state.loading = true;
        this.state.error = "";
        try {
            const data = await this.orm.call(
                "biz.smart.finance.dashboard", method, [this.rpcFilters]);
            if (requestId !== this._loadRequestId) {
                return;
            }
            this.state.data = {
                ...this.state.data,
                filters: data.filters,
                [key]: data[key],
                updated_at: data.updated_at,
            };
            this.applyFilters(data.filters);
        } catch (error) {
            if (requestId === this._loadRequestId) {
                this.state.error = (error.data && error.data.message) || String(error);
            }
        } finally {
            if (requestId === this._loadRequestId) {
                this.state.loading = false;
            }
        }
    }

    /** เปลี่ยนศูนย์ต้นทุนพร้อม Overview และล้างสไลซ์ช่องทางที่อิง plan เดิม */
    async setPlan(planId) {
        if (String(planId) === this.state.planId) {
            return;
        }
        this.state.planId = String(planId);
        await this.load();
    }

    /** เปลี่ยนโหมด/จำนวนช่วงของแท็บ Compare — คำนวณทุกคอลัมน์ที่ฝั่ง server */
    async setCompare(mode, count) {
        const nextCount = String(count || 4);
        if (mode === this.state.compareMode
                && nextCount === this.state.compareCount) {
            return;
        }
        this.state.compareMode = mode || "";
        this.state.compareCount = nextCount;
        // Overview includes the comparison headline, so refresh both together.
        await this.load();
    }

    /**
     * เปลี่ยนมิติ/ช่องทางของแท็บ Sales Channel — คิดทั้งหมดที่ฝั่ง server
     * แต่กระทบแท็บเดียว จึงโหลดเฉพาะสไลซ์ channel
     */
    async setChannel(dim, channelId) {
        const nextId = String(channelId || "");
        if (dim === this.state.channelDim && nextId === this.state.channelId) {
            return;
        }
        this.state.channelDim = dim || "partner";
        this.state.channelId = nextId === "0" ? "" : nextId;
        await this.loadSlice("get_channel_data", "channel");
    }

    async setScenario(code) {
        if (this.state.scenario === code) {
            return;
        }
        this.state.scenario = code;
        await this.load();
    }

    async setTab(tab) {
        // การ์ดที่กางอยู่ถูก unmount ไปพร้อมแท็บเดิม — ต้องหุบก่อน
        // ไม่งั้นฉากหลังทึบจะค้างอยู่บนแท็บใหม่โดยไม่มีอะไรให้ปิด
        this.closeZoom();
        this.state.tab = tab;
        const group = this.menuGroups.find((item) =>
            item.tabs.some((child) => child.id === tab));
        if (group) {
            this.state.menuGroup = group.id;
        }
        // แท็บช่องทางขายไม่ได้อยู่ใน payload หลัก (คิดงบรายเดือนทั้งปีงบ)
        // — โหลดสไลซ์ของมันครั้งแรกที่เปิดเท่านั้น
        if (tab === "channel" && this.state.data && !this.state.data.channel) {
            await this.loadSlice("get_channel_data", "channel");
        }
    }

    setUnit(unit) {
        this.state.unit = unit;
        writePref("bsf_unit", unit);
    }

    /** กาง/หุบรายการข้อมูลที่ยังไม่ได้ตั้งค่า (จำไว้ต่อเครื่อง) */
    toggleHints() {
        this.state.hintsOpen = !this.state.hintsOpen;
        writePref("bsf_hints", this.state.hintsOpen ? "1" : "0");
    }

    toggleTheme() {
        this.state.theme = this.state.theme === "dark" ? "light" : "dark";
        writePref("bsf_theme", this.state.theme);
    }

    goBack() {
        this.env.config.historyBack();
    }

    print() {
        window.print();
    }

    /**
     * ส่งออกงบการเงินเป็น PDF/Excel — ส่งแค่ filters ให้ server
     * ตัวเลขทั้งหมด engine ดึงเองฝั่ง server (กติกาเดียวกับ AI brief)
     */
    async exportReport(output) {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = output;
        try {
            const action = await this.orm.call(
                "biz.smart.finance.export.wizard", "action_export",
                [this.rpcFilters, output]);
            await this.action.doAction(action);
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || String(error),
                { type: "danger" });
        } finally {
            this.state.exporting = "";
        }
    }

    get menuGroups() {
        return [
            {
                id: "overview", icon: "fa-th-large", label: "ภาพรวม",
                tabs: [
                    { id: "overview", icon: "fa-th-large", label: "Overview", sub: "ภาพรวม" },
                ],
            },
            {
                id: "finance", icon: "fa-pie-chart", label: "การเงิน",
                tabs: [
                    { id: "cash", icon: "fa-line-chart", label: "Cash & Liquidity", sub: "เงินสด" },
                    { id: "statements", icon: "fa-balance-scale", label: "Statements", sub: "งบการเงิน" },
                    { id: "ratios", icon: "fa-calculator", label: "Financial Ratios", sub: "อัตราส่วนการเงิน" },
                    { id: "compare", icon: "fa-bar-chart", label: "Compare (BI)", sub: "เปรียบเทียบหลายงวด" },
                    { id: "controlling", icon: "fa-sitemap", label: "Controlling", sub: "ศูนย์ต้นทุน" },
                    { id: "ap", icon: "fa-calendar-check-o", label: "AP & Payment Plan", sub: "แผนจ่าย" },
                    { id: "cost", icon: "fa-calculator", label: "ต้นทุนและจุดคุ้มทุน" },
                ],
            },
            {
                id: "sales", icon: "fa-shopping-cart", label: "การขาย",
                tabs: [
                    { id: "sales", icon: "fa-filter", label: "Sales to Cash", sub: "ขาย→เก็บเงิน" },
                    { id: "channel", icon: "fa-shopping-basket", label: "Sales Channel", sub: "วิเคราะห์ช่องทางขาย" },
                    { id: "margin", icon: "fa-pie-chart", label: "Project Margin", sub: "กำไรโครงการ" },
                ],
            },
            {
                id: "operations", icon: "fa-cog", label: "การปฏิบัติการ",
                tabs: [
                    { id: "inventory", icon: "fa-cubes", label: "Inventory", sub: "สินค้าคงเหลือ" },
                ],
            },
            {
                id: "planning", icon: "fa-bullseye", label: "การวางแผน",
                tabs: [
                    { id: "strategy", icon: "fa-bullseye", label: "กลยุทธ์และ Action" },
                    { id: "forecast", icon: "fa-area-chart", label: "Forecast", sub: "พยากรณ์รายเดือน" },
                    { id: "risk", icon: "fa-exclamation-triangle", label: "Risk Radar", sub: "ความเสี่ยง" },
                    { id: "ai", icon: "fa-magic", label: "AI Copilot", sub: "ผู้ช่วย AI" },
                ],
            },
        ];
    }

    get activeMenuGroup() {
        return this.menuGroups.find((group) => group.id === this.state.menuGroup)
            || this.menuGroups[0];
    }

    selectMenuGroup(group) {
        this.state.menuGroup = group.id;
        const current = group.tabs.some((tab) => tab.id === this.state.tab);
        if (!current && group.tabs[0]) {
            this.setTab(group.tabs[0].id);
        }
    }

    get tabs() {
        return this.activeMenuGroup.tabs;
    }

    get monthNames() {
        return MONTH_NAMES;
    }

    openHint(hint) {
        if (!hint.model) {
            // hint ที่ไม่มี model (เช่น no_ai_key) → เปิด General Settings
            this.action.doAction("base_setup.action_general_configuration");
            return;
        }
        this.openList(hint.message, hint.model, []);
    }
}

registry.category("actions").add("biz_smart_finance.dashboard", BsfDashboard);
