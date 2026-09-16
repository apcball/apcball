/** @odoo-module **/

import { useState } from "@odoo/owl";
import { BsfTab, buildBarLine, CMP_MODES, CMP_COUNTS } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

const MODES = CMP_MODES;
const COUNTS = CMP_COUNTS;

// การ์ดกราฟกินเต็มความกว้าง — viewBox ต้องกว้างตาม ไม่งั้น svg ที่ยืดเต็มจอ
// จะสูงตามอัตราส่วนเดิม (640×240 ที่ 1500px = สูง ~560px) กลืนทั้งหน้า
const CHART_SIZE = { width: 1180, height: 260 };

/**
 * Compare (BI) — งบหลายงวดเรียงเป็นคอลัมน์ + กราฟแนวโน้มของแถวที่เลือก
 *
 * โหมด/จำนวนช่วงต้องยิง server ใหม่ (aggregation อยู่ฝั่งนั้น) ส่วนการเลือก
 * แถวขึ้นกราฟและการโชว์ Δ% เป็น state ฝั่ง client ล้วน ไม่ต้อง reload
 */
export class BsfTabCompare extends BsfTab {
    static template = "biz_smart_finance.TabCompare";
    static components = { BsfAiCard };
    static props = { data: Object, unit: String, onCompare: Function };

    setup() {
        super.setup();
        this.modes = MODES;
        this.counts = COUNTS;
        this.state = useState({ metric: "revenue_op", showDelta: true });
    }

    get cmp() {
        return this.props.data.compare;
    }

    /** สามบล็อกเงิน: งบกำไรขาดทุน (ยอดไหล) / ฐานะการเงิน (ยอดสะสม) /
     *  กระแสเงินสด (กระแสในงวด) */
    get sections() {
        return [
            {
                key: "pnl",
                label: "งบกำไรขาดทุน",
                sub: "ยอดไหลภายในงวดของคอลัมน์",
                rows: this.cmp.pnl_rows,
            },
            {
                key: "bs",
                label: "ฐานะการเงิน",
                sub: "ยอดคงเหลือ ณ วันสิ้นคอลัมน์",
                rows: this.cmp.bs_rows,
            },
            {
                key: "cf",
                label: "งบกระแสเงินสด",
                sub: "กระแสเงินสดในงวดของคอลัมน์",
                rows: this.cmp.cf_rows || [],
            },
        ];
    }

    /** ทุกแถวที่ขึ้นกราฟได้ (เงิน + KPI %)
     *  เทมเพลตอ้าง metrics/activeMetric ทั้งใน t-foreach ของชิป และผ่าน
     *  isActiveRow() สองครั้งต่อแถวตาราง — ถ้าไม่จำไว้ ลิสต์ ~40 รายการจะถูก
     *  สร้างใหม่กว่าร้อยรอบต่อการ render หนึ่งครั้ง */
    get metrics() {
        return this.memoChart("metrics", [this.cmp], () => {
            const list = [];
            const money = [
                ...this.cmp.pnl_rows, ...this.cmp.bs_rows,
                ...(this.cmp.cf_rows || []),
            ];
            for (const row of money) {
                list.push({ key: row.key, label: row.label, unit: "money", row });
            }
            for (const row of this.cmp.kpi_rows) {
                list.push({ key: row.key, label: row.label, unit: "pct", row });
            }
            return list;
        });
    }

    get activeMetric() {
        return this.memoChart(
            "activeMetric", [this.cmp, this.state.metric], () => {
                const list = this.metrics;
                return list.find((m) => m.key === this.state.metric) || list[0];
            });
    }

    isActiveRow(row) {
        const active = this.activeMetric;
        return Boolean(active) && active.key === row.key;
    }

    selectMetric(key) {
        this.state.metric = key;
    }

    toggleDelta() {
        this.state.showDelta = !this.state.showDelta;
    }

    /**
     * แท่ง = แถวเงิน (scale ก่อนส่ง builder ตามกติกา unit) / เส้น = แถว %
     * ใช้สเกลแกนเดียวเสมอ จึงไม่ผสมเงินกับเปอร์เซ็นต์ในกราฟเดียว
     */
    get metricChart() {
        return this.memoChart(
            "metricChart", [this.cmp, this.state.metric, this.unit], () =>
                this._buildMetricChart());
    }

    _buildMetricChart() {
        const metric = this.activeMetric;
        const labels = this.cmp.columns.map((col) => col.label);
        const raw = (metric ? metric.row.values : []).map((v) => Number(v || 0));
        if (metric && metric.unit === "pct") {
            return buildBarLine(labels, [], [{
                key: metric.key,
                label: metric.label,
                cls: "line_actual",
                values: raw,
            }], CHART_SIZE);
        }
        return buildBarLine(
            labels, raw.map((v) => this.scale(v)), [], CHART_SIZE,
        );
    }

    get chartIsMoney() {
        const metric = this.activeMetric;
        return !metric || metric.unit === "money";
    }

    /** ป้ายแกนตั้ง: เงินคิดตาม unit ปัจจุบัน ส่วน % แสดงดิบ */
    fmtChartAxis(value) {
        return this.chartIsMoney
            ? this.fmtAxis(value)
            : `${Number(value || 0).toFixed(0)}%`;
    }

    fmtCell(row, index) {
        return this.fmtMoney(row.values[index]);
    }

    // ---------------- ตัวกรองที่ต้องยิง server ----------------
    onModeChange(ev) {
        this.props.onCompare(ev.target.value, this.cmp.count);
    }

    onCountChange(ev) {
        this.props.onCompare(this.cmp.mode, parseInt(ev.target.value, 10));
    }

    enable() {
        this.props.onCompare(this.cmp.mode || "month", this.cmp.count || 4);
    }

    // ---------------- drill-down ----------------
    /**
     * ช่องหนึ่ง = แถวหนึ่ง × คอลัมน์หนึ่ง → รายการบัญชีในหน้าต่างของคอลัมน์นั้น
     * ใช้วันที่จาก payload ของคอลัมน์โดยตรง ไม่ใช่ helper ปีงบกลาง (fyFrom
     * ยึดปีปฏิทิน จึงผิดกับปีงบที่ไม่ตรงปฏิทินและกับคอลัมน์ย้อนหลัง)
     */
    openCell(row, colIndex) {
        this.openCmpCell(row, this.cmp.columns[colIndex]);
    }

    openBar(bar) {
        const metric = this.activeMetric;
        if (metric && metric.unit === "money") {
            this.openCell(metric.row, bar.index);
        }
    }
}
