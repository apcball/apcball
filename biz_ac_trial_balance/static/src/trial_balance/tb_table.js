/** @odoo-module **/

import { Component } from "@odoo/owl";
import { fmtNum } from "@biz_ac_trial_balance/trial_balance/tb_format";

/**
 * ตารางงบทดลอง
 *
 * เซิร์ฟเวอร์ส่งแถวมาเป็น flat list เรียงตามลำดับที่จะแสดงอยู่แล้ว (หัวหมวด → บัญชี →
 * รวมหมวด) ฝั่ง client จึงแค่วาดตามลำดับนั้น ตารางเดียวกันนี้พิมพ์ลง PDF/Excel ได้
 * โดยไม่ต้องมีตรรกะซ้ำ
 */
export class TbTable extends Component {
    static template = "biz_ac_trial_balance.TbTable";
    static props = {
        data: Object,
        onDrillDown: Function,
    };

    get columns() {
        const cols = [
            { key: "code", label: "เลขที่บัญชี", type: "code" },
            { key: "name", label: "ชื่อบัญชี", type: "name" },
        ];
        // โหมดแยกบริษัทต้องบอกให้ได้ว่าแถวไหนของใคร ไม่งั้นเห็นรหัสซ้ำแล้วงง
        if (
            this.props.data.options.company_mode === "split" &&
            this.props.data.company.count > 1
        ) {
            cols.push({ key: "company_name", label: "บริษัท", type: "text" });
        }
        cols.push(
            { key: "opening_debit", group: "ยอดยกมา", label: "เดบิต", type: "num" },
            { key: "opening_credit", group: "ยอดยกมา", label: "เครดิต", type: "num" },
            { key: "period_debit", group: "เปลี่ยนแปลง", label: "เดบิต", type: "num" },
            { key: "period_credit", group: "เปลี่ยนแปลง", label: "เครดิต", type: "num" },
            { key: "closing_debit", group: "คงเหลือ", label: "เดบิต", type: "num" },
            { key: "closing_credit", group: "คงเหลือ", label: "เครดิต", type: "num" }
        );
        if (this.props.data.options.compare !== "none") {
            const label = this.props.data.labels.compare || "เปรียบเทียบ";
            cols.push(
                { key: "compare_debit", group: label, label: "เดบิต", type: "num" },
                { key: "compare_credit", group: label, label: "เครดิต", type: "num" }
            );
        }
        cols.push({ key: "change_pct", label: "เปลี่ยนแปลง %", type: "pct" });
        cols.push({ key: "flag", label: "", type: "flag" });
        return cols;
    }

    /** หัวตารางแถวบน: กลุ่มคอลัมน์ที่ merge แล้ว */
    get headerGroups() {
        const groups = [];
        for (const col of this.columns) {
            const last = groups[groups.length - 1];
            if (col.group && last && last.label === col.group) {
                last.span += 1;
            } else if (col.group) {
                groups.push({ label: col.group, span: 1, isGroup: true });
            } else {
                groups.push({ label: col.label, span: 1, isGroup: false });
            }
        }
        return groups;
    }

    rowClass(line) {
        const classes = ["tb-row", `tb-row-${line.kind}`];
        if (line.flag === "abnormal") {
            classes.push("tb-row-abnormal");
        }
        if (line.kind === "account" && line.account_id) {
            classes.push("tb-row-clickable");
        }
        return classes.join(" ");
    }

    cellValue(line, col) {
        // แถวหัวหมวดเป็นแค่ป้ายกำกับ ไม่มีตัวเลขของตัวเอง
        // และ % ของยอดรวมทั้งสิ้นไม่มีความหมาย (เดบิต/เครดิตแยกคอลัมน์กันอยู่แล้ว)
        if (line.kind === "section") {
            return "";
        }
        const value = line[col.key];
        if (col.type === "num") {
            return value ? fmtNum(value) : "";
        }
        if (col.type === "pct") {
            return value === null || value === undefined ? "" : `${fmtNum(value, 1)}%`;
        }
        return value || "";
    }

    onRowClick(line) {
        if (line.kind === "account" && line.account_id) {
            this.props.onDrillDown(line);
        }
    }
}
