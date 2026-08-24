/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { fmtNum } from "@biz_ac_trial_balance/trial_balance/tb_format";
import { TbFilterBar } from "@biz_ac_trial_balance/trial_balance/tb_filter_bar";
import { TbTable } from "@biz_ac_trial_balance/trial_balance/tb_table";

/**
 * หน้าจองบทดลอง (Trial Balance)
 *
 * ตัวเลขทุกตัวมาจาก biz.trial.balance.report.get_report_data() ตัวเดียวกับที่ PDF และ
 * Excel ใช้ และปุ่มพิมพ์ก็ส่ง options ชุดเดียวกันนี้กลับไป — จอกับไฟล์จึงตรงกันเสมอ
 */
export class TrialBalance extends Component {
    static template = "biz_ac_trial_balance.TrialBalance";
    static components = { TbFilterBar, TbTable };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            data: null,
            // options เริ่มต้นปล่อยให้เซิร์ฟเวอร์เติมให้ (วันที่, ปีบัญชี) จะได้ไม่ต้องมี
            // ตรรกะปีบัญชีสองชุด
            options: this.props.action.context.tb_options || {},
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "biz.trial.balance.report",
                "get_report_data",
                [this.state.options]
            );
            this.state.data = data;
            this.state.options = data.options;
        } finally {
            this.state.loading = false;
        }
    }

    async updateOptions(changes) {
        Object.assign(this.state.options, changes);
        await this.load();
    }

    async drillDown(line) {
        const action = await this.orm.call(
            "biz.trial.balance.report",
            "action_open_journal_items",
            [line.account_ids || line.account_id, this.state.options]
        );
        this.actionService.doAction(action);
    }

    async print(output) {
        const action = await this.orm.call(
            "biz.trial.balance.wizard",
            "action_export_from_options",
            [this.state.options, output]
        );
        this.actionService.doAction(action);
    }

    get summary() {
        const data = this.state.data;
        if (!data) {
            return [];
        }
        return [
            { label: "เดบิตรวม", value: fmtNum(data.totals.closing_debit) },
            { label: "เครดิตรวม", value: fmtNum(data.totals.closing_credit) },
            {
                label: "กำไร(ขาดทุน)สุทธิของงวด",
                value: fmtNum(data.totals.net_profit || 0),
            },
            { label: "จำนวนบัญชี", value: String(this.accountCount) },
        ];
    }

    get accountCount() {
        return this.state.data
            ? this.state.data.lines.filter((l) => l.kind === "account").length
            : 0;
    }
}

registry.category("actions").add("biz_ac_trial_balance.trial_balance", TrialBalance);
