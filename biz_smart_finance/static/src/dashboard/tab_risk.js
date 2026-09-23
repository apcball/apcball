/** @odoo-module **/

import { useState } from "@odoo/owl";
import { BsfTab, heatColor, niceMax, riskBand } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

// สถานะของ "แผนรับมือ" — no_plan คือแถวที่ระบบตรวจเจอเองและยังไม่มีใครถือ
const STATUS_COLORS = {
    not_started: "var(--bsf-neutral)",
    in_progress: "var(--bsf-warn)",
    at_risk: "var(--bsf-risk)",
    done: "var(--bsf-good)",
    no_plan: "var(--bsf-risk)",
};

const SCENARIO_LABELS = {
    base: "Base",
    downside: "Downside",
    stress: "Stress",
};

export class BsfTabRisk extends BsfTab {
    static template = "biz_smart_finance.TabRisk";
    static components = { BsfAiCard };
    static props = {
        data: Object, unit: String, onScenario: Function, onUnit: Function,
    };

    setup() {
        super.setup();
        // ช่วงเวลา/ตัวเทียบเปลี่ยนบนจอล้วน ๆ — engine ส่งทุกช่วงทุก scenario
        // มาแล้วตั้งแต่ตอนโหลด (ดู _risk_outcomes) จึงไม่ต้องยิงเซิร์ฟเวอร์ใหม่
        this.state = useState({ horizon: 0, compare: "base" });
    }

    get risk() {
        return this.props.data.risk;
    }

    get scenario() {
        return this.risk.scenario;
    }

    get scenarios() {
        return ["base", "downside", "stress"].map((code) => ({
            code, label: SCENARIO_LABELS[code],
        }));
    }

    scenarioLabel(code) {
        return SCENARIO_LABELS[code] || code;
    }

    get horizons() {
        return this.risk.horizons || [];
    }

    /** ช่วงที่กำลังดู — ตั้งต้น 6 เดือน หรือช่วงที่ยาวที่สุดที่พยากรณ์ไปถึง */
    get horizon() {
        const list = this.horizons;
        if (list.includes(this.state.horizon)) {
            return this.state.horizon;
        }
        return list.includes(6) ? 6 : (list[list.length - 1] || 0);
    }

    setHorizon(ev) {
        this.state.horizon = parseInt(ev.target.value) || 0;
    }

    setCompare(ev) {
        this.state.compare = ev.target.value;
    }

    setScenario(code) {
        this.props.onScenario(code);
    }

    setUnit(ev) {
        this.props.onUnit(ev.target.value);
    }

    // ---------------- สมมติฐาน ----------------
    /**
     * การ์ดสมมติฐาน = ค่าของ scenario ปัจจุบัน "ลบ" ค่าของตัวที่เลือกเทียบ
     * (เทียบกับ Base ตามค่าตั้งต้น) — ทั้งสองชุดเรียงลำดับเดียวกันจาก engine
     */
    get assumptionTiles() {
        const active = this.risk.assumptions[this.scenario] || [];
        const reference = this.risk.assumptions[this.state.compare] || [];
        return active.map((tile, index) => {
            const base = reference[index] || { value: 0 };
            return { ...tile, delta: tile.value - base.value };
        });
    }

    fmtAssumption(tile) {
        const value = tile.delta;
        if (!value) {
            return "±0";
        }
        return `${value > 0 ? "+" : "−"}${this.fmtNum(Math.abs(value), tile.digits)}`;
    }

    assumptionTip(tile) {
        const scope = tile.engine
            ? "ตัวคูณที่ engine ใช้จริงกับทุกแท็บ (เงินสด / พยากรณ์ / กำไรโครงการ)"
            : "ใช้กับ Key Outcome และ Sensitivity ของแท็บนี้เท่านั้น";
        return `${tile.label} — ${scope}\nตั้งค่าได้ที่ Finance Settings ของแต่ละบริษัท`;
    }

    // ---------------- Key Outcome ----------------
    get outcome() {
        const bucket = this.risk.outcomes[String(this.horizon)] || {};
        return bucket[this.scenario] || null;
    }

    get reference() {
        const bucket = this.risk.outcomes[String(this.horizon)] || {};
        return bucket[this.state.compare] || null;
    }

    /** สามการ์ดผลลัพธ์ — ตัวเลขดิบทั้งคู่ ให้ template เป็นคนจัดรูปแบบ */
    get outcomeCards() {
        const now = this.outcome;
        const ref = this.reference;
        if (!now) {
            return [];
        }
        const delta = (key) => (
            now[key] === null || !ref || ref[key] === null
                ? null : now[key] - ref[key]
        );
        return [
            {
                code: "runway",
                icon: "fa-clock-o",
                label: "Cash Runway",
                label_th: "ระยะเวลาคงเหลือของเงินสด",
                value: now.runway_months,
                ref: ref ? ref.runway_months : null,
                delta: delta("runway_months"),
                unit: "เดือน",
                kind: "months",
                note: this.risk.min_cash
                    ? `เกณฑ์ขั้นต่ำ ${this.fmtMoney(this.risk.min_cash)} ${this.unitLabel}`
                    : "ยังไม่ได้ตั้งเงินสดขั้นต่ำ — นับถึงศูนย์",
            },
            {
                code: "min_cash",
                icon: "fa-tint",
                label: "Minimum Cash",
                label_th: "เงินสดต่ำสุด",
                value: now.min_cash,
                ref: ref ? ref.min_cash : null,
                delta: delta("min_cash"),
                unit: this.unitLabel,
                kind: "money",
                note: `เดือนที่ต่ำสุด: ${now.min_cash_month}`,
            },
            {
                code: "headroom",
                icon: "fa-balance-scale",
                label: "Covenant Headroom",
                label_th: "วงเงินคงเหลือภายใต้เงื่อนไขสัญญา",
                value: now.headroom,
                ref: ref ? ref.headroom : null,
                delta: delta("headroom"),
                unit: this.unitLabel,
                kind: "money",
                note: this.risk.nde_target === null
                    ? "ยังไม่ได้ตั้งเป้า Net Debt / Equity"
                    : `เป้า Net Debt / Equity < ${this.fmtNum(this.risk.nde_target, 2)}x`
                      + ` · ตอนนี้ ${now.nde_ratio === null ? "—" : this.fmtNum(now.nde_ratio, 2) + "x"}`,
            },
        ];
    }

    /** ยอดเงินติดลบบนการ์ดผลลัพธ์ = สัญญาณอันตราย ต้องเห็นเป็นสีทันที */
    outcomeClass(card) {
        return card.value !== null && card.value < 0 ? "is-alert" : "";
    }

    /** ค่าบนการ์ด: เดือนใช้ทศนิยมเดียว, เงินใช้หน่วยที่เลือกอยู่ */
    outcomeValue(card) {
        if (card.value === null || card.value === undefined) {
            return "—";
        }
        return card.kind === "months"
            ? this.fmtNum(card.value, 1) : this.fmtMoney(card.value);
    }

    outcomeDelta(card) {
        if (card.delta === null || card.delta === undefined) {
            return "";
        }
        const sign = card.delta > 0 ? "+" : "−";
        const body = card.kind === "months"
            ? this.fmtNum(Math.abs(card.delta), 1)
            : this.fmtMoney(Math.abs(card.delta));
        return `${sign}${body}`;
    }

    /** runway ที่เป็น null = เงินสดไม่แตะเกณฑ์เลยในช่วงที่พยากรณ์ไปถึง */
    outcomeSub(card) {
        if (card.value === null && card.code === "runway") {
            return `ไม่แตะเกณฑ์ภายใน ${this.horizon} เดือน`;
        }
        if (card.ref === null || card.ref === undefined) {
            return "";
        }
        const body = card.kind === "months"
            ? this.fmtNum(card.ref, 1) : this.fmtMoney(card.ref);
        return `${this.scenarioLabel(this.state.compare)}: ${body}`;
    }

    // ---------------- Sensitivity (ตอร์นาโด) ----------------
    /**
     * แท่งสองข้างของศูนย์ — ซ้าย (แดง) = ผลกระทบด้านลบตามขนาดช็อก
     * ขวา (เขียวน้ำเงิน) = ผลด้านบวกขนาดเท่ากันถ้าช็อกกลับทาง
     */
    get tornado() {
        return this.memoChart(
            "tornado", [this.risk, this.horizon, this.unit], () =>
                this._buildTornado());
    }

    _buildTornado() {
        const rows = this.risk.sensitivity[String(this.horizon)] || [];
        const labelW = 210;
        const width = 660;
        const rowH = 34;
        const padTop = 30;
        const padBottom = 18;
        const height = padTop + rows.length * rowH + padBottom;
        const right = width - 16;
        const center = labelW + (right - labelW) / 2;
        const half = (right - labelW) / 2 - 46;
        const values = rows.map((row) => this.scale(row.amount));
        const max = niceMax(Math.max(...values, 0.001));
        const at = (value) => (max ? (value / max) * half : 0);
        return {
            width, height, center, labelW, padTop, rowH,
            axisTop: padTop - 12,
            axisBottom: padTop + rows.length * rowH,
            max,
            ticks: [-1, -0.5, 0, 0.5, 1].map((factor) => ({
                x: center + half * factor,
                value: max * factor,
            })),
            rows: rows.map((row, index) => {
                const value = values[index];
                const length = at(value);
                return {
                    ...row,
                    value,
                    index,
                    // ช็อกที่คิดออกมาได้ศูนย์ (ยังไม่มีข้อมูลฐาน) — ไม่ต้องวาด
                    // แท่งกับป้าย "−0 / +0" ให้รกแถว
                    zero: !length,
                    y: padTop + index * rowH,
                    barY: padTop + index * rowH + 7,
                    textY: padTop + index * rowH + 18,
                    negX: center - length,
                    posX: center,
                    length,
                    negLabelX: center - length - 6,
                    posLabelX: center + length + 6,
                };
            }),
        };
    }

    sensitivityTip(row) {
        const kind = row.basis === "cash"
            ? "กระทบกระแสเงินสดในช่วงที่เลือก"
            : "กระทบ EBITDA ในช่วงที่เลือก";
        return `${row.label_th} (${row.shock}) — ${kind}`;
    }

    // ---------------- แมทริกซ์ความเสี่ยง ----------------
    get matrix() {
        return this.risk.matrix;
    }

    cellColor(cell) {
        return cell.count ? heatColor(cell.score) : "";
    }

    cellTip(row, cell) {
        if (!cell.count) {
            return `${row.label} — ไม่มีความเสี่ยงในช่องนี้`;
        }
        return `${row.label} — ${cell.count} ความเสี่ยง · คะแนนสูงสุด `
            + `${cell.score}\nคลิกเพื่อดูรายการ`;
    }

    get matrixLegend() {
        return [
            { label: "ต่ำ 1–7", color: heatColor(1) },
            { label: "กลาง 8–14", color: heatColor(8) },
            { label: "สูง 15–19", color: heatColor(15) },
            { label: "วิกฤต 20–25", color: heatColor(20) },
        ];
    }

    band(score) {
        return riskBand(score);
    }

    // ---------------- ตาราง Early-Warning ----------------
    statusColor(code) {
        return STATUS_COLORS[code] || "var(--bsf-neutral)";
    }

    // ---------------- drill-down ----------------
    openRisk(row) {
        if (row.id) {
            this.openForm("biz.smart.finance.risk", row.id);
        }
    }

    openRegister() {
        this.openList("Risk Register", "biz.smart.finance.risk", []);
    }

    /** ช่องแมทริกซ์ → ความเสี่ยงของโครงการนั้นในคอลัมน์นั้น */
    openCell(row, cell) {
        if (!cell.count) {
            return;
        }
        const axis = this.matrix.axis === "company"
            ? ["company_id", "=", parseInt(cell.column)]
            : ["category", "=", cell.column];
        this.openList(
            `${row.label} — ความเสี่ยง`, "biz.smart.finance.risk", [
                ["project_id", "=", row.project_id || false],
                axis,
                ["state", "!=", "closed"],
                ...this.companyDomain(),
            ]);
    }

    openConfig() {
        this.openList(
            "Finance Settings", "biz.smart.finance.config",
            this.companyDomain());
    }
}
