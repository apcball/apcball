/** @odoo-module **/
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class BsfTabStrategy extends Component {
    static template = "biz_smart_finance.TabStrategy";
    static props = ["filters", "mode", "unit"];
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ data: null, loading: true, error: "", evaluating: false });
        this.sequence = 0;
        onWillStart(() => this.load(this.props));
        onWillUpdateProps((next) => {
            if (JSON.stringify(next.filters) !== JSON.stringify(this.props.filters) || next.mode !== this.props.mode) {
                return this.load(next);
            }
        });
    }
    async load(props = this.props) {
        const seq = ++this.sequence;
        this.state.loading = true;
        this.state.error = "";
        try {
            const data = await this.orm.call("biz.smart.finance.strategy.service",
                props.mode === "cost" ? "get_cost_data" : "get_strategy_data", [props.filters]);
            if (seq === this.sequence) this.state.data = data;
        } catch (error) {
            if (seq === this.sequence) this.state.error = error.data?.message || String(error);
        } finally {
            if (seq === this.sequence) this.state.loading = false;
        }
    }
    money(value) {
        if (value === null || value === undefined) return "—";
        return (value / (this.props.unit === "mb" ? 1000000 : 1)).toLocaleString("th-TH", {maximumFractionDigits: 2});
    }
    number(value) {
        return value === null || value === undefined ? "—" : value.toLocaleString("th-TH", {maximumFractionDigits: 2});
    }
    get metrics() {
        return [
            {key: "sales", label: "ยอดขายสุทธิ"}, {key: "variable", label: "ต้นทุนผันแปร"},
            {key: "fixed", label: "ต้นทุนคงที่"}, {key: "one_off", label: "ค่าใช้จ่ายครั้งเดียว"},
            {key: "cost", label: "ต้นทุนดำเนินงานรวม"}, {key: "budget", label: "งบต้นทุน"},
            {key: "personnel", label: "เงินเดือน OT และสวัสดิการ"},
            {key: "personnel_pct", label: "บุคลากร / ยอดขาย (%)", ratio: true},
            {key: "ot", label: "OT"}, {key: "fte", label: "FTE", ratio: true},
            {key: "sales_per_fte", label: "ยอดขาย / FTE"}, {key: "contribution_per_fte", label: "กำไรส่วนเกิน / FTE"},
            {key: "contribution", label: "กำไรส่วนเกิน"},
            {key: "contribution_pct", label: "อัตรากำไรส่วนเกิน (%)", ratio: true},
            {key: "operating_profit", label: "กำไรดำเนินงาน"}, {key: "recurring_profit", label: "กำไรก่อนค่าใช้จ่ายครั้งเดียว"},
            {key: "break_even", label: "ยอดขายคุ้มทุน"}, {key: "recurring_break_even", label: "คุ้มทุนก่อนค่าใช้จ่ายครั้งเดียว"},
            {key: "target_sales", label: "ยอดขายเพื่อกำไรเป้า"}, {key: "sales_gap", label: "ยอดขายขาดจากคุ้มทุน"},
            {key: "safety_margin", label: "ยอดขายเหนือจุดคุ้มทุน"},
        ];
    }
    open(model, id) {
        return this.action.doAction({type: "ir.actions.act_window", res_model: `biz.smart.finance.${model}`,
            res_id: id, views: [[false, "form"]], target: "current"});
    }
    openList(xmlid) {
        return this.action.doAction(`biz_smart_finance.action_bsf_${xmlid}`, {
            additionalContext: this.props.filters.company_id ? {default_company_id: this.props.filters.company_id} : {},
        });
    }
    async evaluate() {
        this.state.evaluating = true;
        try {
            const result = await this.orm.call("biz.smart.finance.strategy.service", "action_evaluate", [this.props.filters]);
            this.notification.add(`ประเมินและอัปเดต ${result.evaluated} ประเด็น`, {type: "success"});
            await this.load();
        } catch (error) {
            this.notification.add(error.data?.message || String(error), {type: "danger"});
        } finally { this.state.evaluating = false; }
    }
    async createAction(issueId) {
        try {
            const action = await this.orm.call("biz.smart.finance.issue", "action_create_action", [[issueId]]);
            await this.action.doAction(action);
        } catch (error) { this.notification.add(error.data?.message || String(error), {type: "danger"}); }
    }
}
