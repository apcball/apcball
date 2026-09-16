/** @odoo-module **/

import { useState } from "@odoo/owl";
import { BsfTab } from "./bsf_widgets";

/**
 * Sales Channel — งบกำไรขาดทุนรายเดือนแยกช่องทางขาย + งบกระแสเงินสดรายเดือน
 *
 * แท็บนี้โหลดสไลซ์ของตัวเอง (`get_channel_data`) ตอนเปิดครั้งแรก payload
 * จึงเป็น null ได้ในเฟรมแรก — ทุก getter ต้องทนกับกรณีนั้น
 *
 * มิติช่องทาง/ช่องทางที่เลือก = ตัวกรองฝั่ง server (aggregation อยู่ที่นั่น)
 * ส่วน metric ของตารางเทียบ กับสวิตช์ "รวมส่วนที่เฉลี่ย" เป็น state ฝั่ง
 * client ล้วน ไม่ต้อง reload
 */
export class BsfTabChannel extends BsfTab {
    static template = "biz_smart_finance.TabChannel";
    static props = { data: Object, unit: String, onChannel: Function };

    setup() {
        super.setup();
        this.state = useState({ metric: "revenue", showSub: {} });
    }

    get ch() {
        return this.props.data.channel || null;
    }

    get ready() {
        return Boolean(this.ch && this.ch.columns);
    }

    get columns() {
        return this.ch.columns;
    }

    get metricDef() {
        const list = this.ch.matrix.metrics;
        return list.find((m) => m.code === this.state.metric) || list[0];
    }

    selectMetric(code) {
        this.state.metric = code;
    }

    /** ค่าของช่องในตารางเทียบ — เงินหรือ % ตาม metric ที่เลือก */
    matrixCell(row, index) {
        const metric = this.metricDef;
        const value = row.metrics[metric.code][index];
        return metric.unit === "pct" ? this.fmtPct(value) : this.fmtMoney(value);
    }

    matrixTotal(row) {
        const metric = this.metricDef;
        const value = row.totals[metric.code];
        return metric.unit === "pct" ? this.fmtPct(value) : this.fmtMoney(value);
    }

    /**
     * ความเข้มของช่อง = สัดส่วนกับค่าสูงสุดของ metric นั้นทั้งตาราง
     * (จำไว้ต่อ payload+metric — เทมเพลตเรียกทุกช่อง = แถว×เดือน ครั้ง)
     */
    get matrixPeak() {
        return this.memoChart("matrixPeak", [this.ch, this.state.metric], () => {
            const code = this.metricDef.code;
            let peak = 0;
            for (const row of this.ch.matrix.rows) {
                for (const value of row.metrics[code]) {
                    peak = Math.max(peak, Math.abs(Number(value || 0)));
                }
            }
            return peak;
        });
    }

    heatStyle(row, index) {
        const peak = this.matrixPeak;
        const value = Number(row.metrics[this.metricDef.code][index] || 0);
        if (!peak || !value) {
            return "";
        }
        const alpha = Math.min(Math.abs(value) / peak, 1) * 0.3;
        const color = value < 0 ? "var(--bsf-risk)" : "var(--bsf-primary)";
        return `background: color-mix(in srgb, ${color} ${
            Math.round(alpha * 100)}%, transparent);`;
    }

    /** แถวย่อยกาง/หุบ (จำต่อแถว) */
    isOpen(key) {
        return Boolean(this.state.showSub[key]);
    }

    toggleSub(key) {
        this.state.showSub[key] = !this.state.showSub[key];
    }

    /** % ของยอดที่มาจากการเฉลี่ย — ป้ายเตือนบนบรรทัดที่ไม่ได้ผูก GL ตรง ๆ */
    allocatedPct(row) {
        if (!row.allocated) {
            return null;
        }
        let allocated = 0;
        let total = 0;
        for (let i = 0; i < row.values.length; i++) {
            allocated += Math.abs(Number(row.allocated[i] || 0));
            total += Math.abs(Number(row.values[i] || 0));
        }
        return total ? Math.round(allocated / total * 100) : null;
    }

    // ---------------- ตัวกรองที่ต้องยิง server ----------------
    onDimChange(ev) {
        this.props.onChannel(ev.target.value, 0);
    }

    onChannelChange(ev) {
        this.props.onChannel(this.ch.dim, parseInt(ev.target.value, 10) || 0);
    }

    pickChannel(row) {
        if (row.key >= 0) {
            this.props.onChannel(this.ch.dim, row.key);
        }
    }

    clearChannel() {
        this.props.onChannel(this.ch.dim, 0);
    }

    // ---------------- drill-down ----------------
    /** ช่องหนึ่ง = แถวหนึ่ง × เดือนหนึ่ง → journal item ของเดือนนั้น */
    openCell(row, index) {
        this.openCmpCell(row, this.columns[index]);
    }

    /**
     * แถวย่อยไม่มี types/account_ids ครบเหมือนแถวหลัก — ยืมของแถวแม่มาแล้ว
     * ทับด้วยบัญชี/โดเมนของตัวเอง (แถวที่เป็นยอดเฉลี่ยล้วนไม่มีเอกสารต้นทาง
     * จึงคลิกไม่ได้ — extra_domain เป็น null)
     */
    openSubCell(parent, sub, index) {
        if (!sub.extra_domain && !sub.account_ids) {
            return;
        }
        this.openCmpCell({
            label: `${parent.label} · ${sub.name}`,
            types: sub.account_ids ? [] : parent.types,
            account_ids: sub.account_ids || parent.account_ids,
            exclude_ids: sub.account_ids ? [] : parent.exclude_ids,
            extra_domain: sub.extra_domain,
            cumulative: false,
        }, this.columns[index]);
    }

    subClickable(sub) {
        return Boolean(sub.extra_domain || sub.account_ids);
    }
}
