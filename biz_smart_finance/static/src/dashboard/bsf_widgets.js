/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Intl.NumberFormat แพงกว่าการ format หนึ่งค่ามาก และ toLocaleString สร้าง
// formatter ใหม่ทุกครั้งที่เรียก — ตารางของจอนี้เป็นกริดซ้อน (18 เดือน × 10 แถว,
// 13 สัปดาห์ × ธนาคาร, 6 คอลัมน์ × 40 แถว) จึงเรียกหลักพันครั้งต่อ render หนึ่งรอบ
// จำไว้ต่อจำนวนทศนิยม (มีแค่ 0 กับ 1)
const NUM_FORMATTERS = {};
const MONEY_FORMATTERS = {};

function numFormatter(digits) {
    if (!NUM_FORMATTERS[digits]) {
        NUM_FORMATTERS[digits] = new Intl.NumberFormat("th-TH", {
            maximumFractionDigits: digits,
        });
    }
    return NUM_FORMATTERS[digits];
}

function moneyFormatter(digits) {
    if (!MONEY_FORMATTERS[digits]) {
        MONEY_FORMATTERS[digits] = new Intl.NumberFormat("th-TH", {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        });
    }
    return MONEY_FORMATTERS[digits];
}

// สีระดับความเสี่ยง — ใช้ทั้ง chip, heatmap, ตาราง ("สีเดียว = ความหมายเดียว")
export const LEVEL_COLORS = {
    critical: "#be123c", // rose 700
    high: "#f43f5e",     // rose 500
    medium: "#f59e0b",   // amber 500
    low: "#10b981",      // emerald 500
};

// อายุหนี้: เย็น → ร้อน ตามความเก่า (ยิ่งค้างนานยิ่งแดง)
export const AGING_COLORS = ["#0ea5e9", "#f59e0b", "#fb7185", "#e11d48"];

// ชุดสีของ "หมวด/ขั้นตอน" — ชุดเดียวกับ --bsf-c1..c6 ใน scss
export const FUNNEL_COLORS = [
    "#6366f1", "#0ea5e9", "#14b8a6", "#10b981", "#f59e0b", "#ec4899",
];

export const MONTH_NAMES = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
];

// ตัวเลือกโหมด/จำนวนช่วงของการเทียบหลายงวด — ใช้ร่วมกันระหว่างแท็บ Compare (BI)
// กับงบ waterfall ในแท็บ Statements (ทั้งคู่ยิงตัวกรอง compare_mode/compare_count
// ชุดเดียวกัน — เปลี่ยนที่ไหนก็ผลเหมือนกันทั้ง dashboard)
export const CMP_MODES = [
    { code: "month", label: "รายเดือน (งวดบัญชี)" },
    { code: "quarter", label: "รายไตรมาส" },
    { code: "year", label: "รายปีงบ (ถึงงวดเดียวกัน)" },
];

export const CMP_COUNTS = [2, 3, 4, 5, 6];

/** เพดานแกนปัดเป็นเลขกลม อ่านง่าย */
export function niceMax(rawMax) {
    const peak = Math.max(rawMax, 0.001);
    const step = Math.pow(10, Math.floor(Math.log10(peak)));
    return Math.ceil(peak / step) * step;
}

/**
 * กราฟเส้นเงินสด 13 สัปดาห์ — actual ทึบ / forecast เส้นประ / เส้น min-cash
 * ค่าใน values ต้องถูก scale ตาม unit มาแล้วจากแท็บ (builder ไม่รู้จัก unit)
 * รองรับค่าติดลบ (เงินสดคาดการณ์ต่ำกว่าศูนย์ได้จริง)
 * options.subs = บรรทัดที่สองใต้ป้ายแกน X (เช่นวันที่เริ่มสัปดาห์ "01/09")
 * — ถ้ามี จะกันพื้นที่ล่างเพิ่มให้สองบรรทัดไม่ทับกราฟ
 */
export function buildCashChart(labels, values, options = {}) {
    const width = options.width || 640;
    const height = options.height || 250;
    const padX = options.padX || 48;
    const padY = 14;
    const innerW = width - padX - 16;
    const subs = options.subs || [];
    const hasSub = subs.some(Boolean);
    const innerH = height - padY - (hasSub ? 40 : 26);
    const minCash = options.minCash || 0;
    const bufferCash = options.bufferCash || 0;
    const dividerIndex = options.dividerIndex === undefined ? 0 : options.dividerIndex;
    const n = Math.max(values.length, 1);
    const hi = niceMax(Math.max(...values, minCash, bufferCash, 0));
    const lo = Math.min(0, ...values);
    const range = hi - lo || 1;
    const xAt = (i) => padX + (n > 1 ? (i * innerW) / (n - 1) : innerW / 2);
    const yAt = (v) => padY + innerH * (1 - ((v || 0) - lo) / range);
    const points = values.map((v, i) => ({
        x: xAt(i), y: yAt(v), value: v, index: i,
        label: labels[i] || "",
        sub: subs[i] || "",
        // ป้ายท้ายต้องชิดขวา ไม่งั้นโดนขอบ viewBox ตัด
        anchor: i === n - 1 ? "end" : "middle",
        belowMin: minCash ? v < minCash : false,
    }));
    const cut = Math.min(Math.max(dividerIndex, 0), n - 1);
    const coord = (p) => `${p.x},${p.y}`;
    return {
        width, height, padX, padY, innerH, hi, lo,
        labelY: height - (hasSub ? 21 : 6),
        subY: height - 7,
        xAxisY: yAt(0),
        minY: minCash ? yAt(minCash) : -1,
        bufferY: bufferCash ? yAt(bufferCash) : -1,
        actualPolyline: points.slice(0, cut + 1).map(coord).join(" "),
        forecastPolyline: points.slice(cut).map(coord).join(" "),
        points,
        gridlines: [0, 0.25, 0.5, 0.75, 1].map((f) => ({
            v: lo + range * f,
            y: padY + innerH * (1 - f),
        })),
    };
}

/**
 * แท่ง (ยอดจ่ายตามแผน) + เส้นหลายชุด (เงินสดก่อน/หลังจ่าย) + เส้น min-cash
 * ใช้ในแท็บ AP — สเกลแกนเดียวกันทั้งแท่งและเส้น
 */
export function buildBarLine(labels, bars, lineSeries, options = {}) {
    const width = options.width || 640;
    const height = options.height || 250;
    const padX = 48;
    const padY = 14;
    const innerW = width - padX - 16;
    const subs = options.subs || [];
    const hasSub = subs.some(Boolean);
    const innerH = height - padY - (hasSub ? 40 : 26);
    const minCash = options.minCash || 0;
    const n = Math.max(labels.length, 1);
    const all = [...bars];
    for (const serie of lineSeries) {
        all.push(...serie.values);
    }
    const hi = niceMax(Math.max(...all, minCash, 0));
    const lo = Math.min(0, ...all);
    const range = hi - lo || 1;
    const slot = innerW / n;
    const barW = Math.max(slot * 0.45, 4);
    const xAt = (i) => padX + slot * i + slot / 2;
    const yAt = (v) => padY + innerH * (1 - ((v || 0) - lo) / range);
    return {
        width, height, padX, padY, innerH,
        labelY: height - (hasSub ? 21 : 6),
        subY: height - 7,
        xAxisY: yAt(0),
        minY: minCash ? yAt(minCash) : -1,
        bars: bars.map((v, i) => ({
            index: i,
            x: xAt(i) - barW / 2,
            y: Math.min(yAt(v), yAt(0)),
            w: barW,
            h: Math.abs(yAt(0) - yAt(v)),
            value: v,
        })),
        series: lineSeries.map((serie) => ({
            ...serie,
            polyline: serie.values.map((v, i) => `${xAt(i)},${yAt(v)}`).join(" "),
        })),
        labels: labels.map((label, index) => ({
            label, index, x: xAt(index), sub: subs[index] || "",
        })),
        gridlines: [0, 0.25, 0.5, 0.75, 1].map((f) => ({
            v: lo + range * f,
            y: padY + innerH * (1 - f),
        })),
    };
}

/** แถบสัดส่วนแนวนอนซ้อน (AP aging) — คืน % ล้วน */
export function buildStackedBar(values, colors) {
    const total = values.reduce((sum, value) => sum + (value || 0), 0);
    return values.map((value, index) => ({
        index,
        value,
        color: colors[index % colors.length],
        pct: total ? ((value || 0) / total) * 100 : 0,
    }));
}

/**
 * ฟอง Budget margin % (X) × Forecast margin % (Y) ขนาดฟอง = งบโครงการ
 * เส้นทแยง 45° = "ไม่มี leakage" — ใต้เส้นคือกำไรคาดการณ์หลุดจากงบ
 */
export function buildScatter(rows, options = {}) {
    const width = options.width || 520;
    const height = options.height || 340;
    const pad = 44;
    const innerW = width - pad - 16;
    const innerH = height - pad - 14;
    const xs = rows.map((r) => r.budget_margin_pct || 0);
    const ys = rows.map((r) => r.forecast_margin_pct || 0);
    const lo = Math.min(-5, ...xs, ...ys);
    const hi = Math.max(30, ...xs, ...ys);
    const range = hi - lo || 1;
    const maxBudget = rows.reduce(
        (top, row) => Math.max(top, row.budget_total || 0), 0);
    const xAt = (v) => pad + ((v - lo) / range) * innerW;
    const yAt = (v) => 14 + innerH * (1 - (v - lo) / range);
    const step = range > 25 ? 10 : 5;
    const ticks = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
        ticks.push({ v, x: xAt(v), y: yAt(v) });
    }
    return {
        width, height, pad, lo, hi,
        x0: pad, y0: 14, x1: pad + innerW, y1: 14 + innerH,
        diag: {
            x1: xAt(lo), y1: yAt(lo),
            x2: xAt(hi), y2: yAt(hi),
        },
        bubbles: rows.map((row) => ({
            ...row,
            cx: xAt(row.budget_margin_pct || 0),
            cy: yAt(row.forecast_margin_pct || 0),
            r: maxBudget
                ? Math.max(5, Math.sqrt((row.budget_total || 0) / maxBudget) * 22)
                : 6,
        })),
        ticks,
    };
}

/**
 * ระดับของคะแนนความเสี่ยง (impact × likelihood = 1..25)
 * จุดตัดต้องตรงกับ `_compute_score` ของ biz.smart.finance.risk (สูง ≥ 15,
 * กลาง ≥ 8) ไม่งั้นชิประดับในตารางกับสีในแมทริกซ์บอกคนละเรื่อง —
 * "วิกฤต" เป็นการซอยช่วงบนของ "สูง" ออกมา ไม่ใช่สเกลใหม่
 */
export function riskBand(score) {
    if (score >= 20) {
        return "critical";
    }
    if (score >= 15) {
        return "high";
    }
    if (score >= 8) {
        return "medium";
    }
    return "low";
}

/** สีของช่องแมทริกซ์ความเสี่ยงตามคะแนน (ใช้จานเดียวกับชิประดับ) */
export function heatColor(score) {
    return LEVEL_COLORS[riskBand(score)];
}

/**
 * สถานะ "กล่องที่ถูกขยาย" — ใช้ร่วมกันทั้งจอ (โมดูลเดียว = กล่องเดียวที่กางได้)
 * เป็น object ธรรมดา ทุก component ต้องเรียก useState(ZOOM_STATE) ของตัวเอง
 * ไม่งั้นตัวที่ไม่ได้ subscribe จะไม่ re-render ตอนกาง/หุบ
 */
export const ZOOM_STATE = { key: "" };

/** helper กาง/หุบการ์ด — ผสมเข้าได้ทั้ง BsfTab และ component อื่น (AI card) */
export const ZoomMixin = {
    isZoomed(key) {
        return this.zoomState.key === key;
    },

    /** ต่อท้าย class ของ <section class="o_bsf_card"> ผ่าน t-att-class */
    zoomCls(key) {
        return this.isZoomed(key) ? "o_bsf_zoomed" : "";
    },

    toggleZoom(key) {
        this.zoomState.key = this.isZoomed(key) ? "" : key;
    },

    closeZoom() {
        this.zoomState.key = "";
    },
};

/**
 * ฐานร่วมของ root และทุกแท็บ — จุดเดียวที่ scale เงินตาม unit
 * engine ส่ง THB ดิบเสมอ ห้าม scale ซ้ำที่อื่น (ดู docstring ฝั่ง engine)
 */
export class BsfTab extends Component {
    static props = { data: Object, unit: String };

    setup() {
        this.action = useService("action");
        this.zoomState = useState(ZOOM_STATE);
    }

    get unit() {
        return this.props.unit || "mb";
    }

    /**
     * จำผลของ getter ที่แพงไว้จนกว่า "กุญแจ" จะเปลี่ยน
     *
     * OWL ไม่แคช getter — เทมเพลตที่อ้าง `cashChart.padX` สิบกว่าที่ (และอ้าง
     * ซ้ำในทุกรอบของ t-foreach) จึงสร้าง geometry ของกราฟใหม่หลายสิบครั้งต่อ
     * การ render หนึ่งรอบ  ตัวหนักที่สุดคือ scatter ของแท็บ Margin ซึ่ง map/
     * reduce ทุกโครงการทุกครั้ง
     *
     * deps เทียบด้วย === ทีละตัว — ใส่ "ก้อนข้อมูลที่ builder อ่าน" (payload
     * ถูกแทนทั้งก้อนตอนโหลดใหม่ อ้างอิงจึงเปลี่ยน) กับค่าที่มีผลต่อผลลัพธ์
     * เช่น unit และ state ของแท็บ
     */
    memoChart(name, deps, build) {
        this._chartMemo = this._chartMemo || {};
        const hit = this._chartMemo[name];
        if (hit && hit.deps.length === deps.length
                && hit.deps.every((dep, index) => dep === deps[index])) {
            return hit.value;
        }
        const value = build();
        this._chartMemo[name] = { deps, value };
        return value;
    }

    /** THB ดิบ → ค่าตาม unit ปัจจุบัน (ใช้ก่อนส่งเข้า chart builder ด้วย) */
    scale(value) {
        const raw = Number(value || 0);
        return this.unit === "mb" ? raw / 1000000 : raw;
    }

    fmtMoney(value) {
        let v = this.scale(value);
        // โหมดล้านบาท: ทศนิยมเฉพาะยอดเล็กจริง ๆ (< 10M) กัน "32.0" รก ๆ เต็มตาราง
        const digits = this.unit === "mb" ? (Math.abs(v) >= 10 ? 0 : 1) : 0;
        // ยอดติดลบที่ปัดแล้วเป็นศูนย์ต้องไม่โชว์ "-0.0" — ในโหมดล้านบาท
        // เศษเงินหลักร้อยจะกลายเป็นลบศูนย์เต็มตารางทั้งที่ไม่มีอะไรผิด
        if (Math.abs(v) < 0.5 * Math.pow(10, -digits)) {
            v = 0;
        }
        return moneyFormatter(digits).format(v);
    }

    /** สำหรับ label แกนกราฟ — รับค่า "ที่ scale แล้ว" จาก chart builder */
    fmtAxis(value) {
        const v = Number(value || 0);
        const abs = Math.abs(v);
        if (abs >= 1000) {
            return numFormatter(1).format(v / 1000) + "k";
        }
        return numFormatter(abs < 10 ? 1 : 0).format(v);
    }

    fmtNum(value, digits = 1) {
        return numFormatter(digits).format(Number(value || 0));
    }

    fmtInt(value) {
        return numFormatter(0).format(Number(value || 0));
    }

    fmtPct(value) {
        if (value === null || value === undefined) {
            return "—";
        }
        return `${Number(value).toFixed(1)}%`;
    }

    /** YoY delta พร้อมเครื่องหมาย (null = ไม่มีฐานเทียบ) */
    fmtDelta(value) {
        if (value === null || value === undefined) {
            return "—";
        }
        const v = Number(value);
        return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
    }

    deltaClass(value, goodWhenUp = true) {
        if (value === null || value === undefined || !Number(value)) {
            return "is-flat";
        }
        const up = Number(value) > 0;
        return up === goodWhenUp ? "is-up" : "is-down";
    }

    zero(value) {
        return Number(value || 0) ? "" : " is-zero";
    }

    levelColor(code) {
        return LEVEL_COLORS[code] || "#94a3b8";
    }

    /** สกุลนำเสนอที่ engine ยืนยันมา (ไม่ใช่ THB ตายตัว — กลุ่มอาจคอนโซลิเดต
     *  เป็นสกุลอื่น) root component ใช้ state.data จึงต้องกันกรณี props ว่าง */
    get currencyName() {
        const data = this.props.data || (this.state && this.state.data);
        return (data && data.filters && data.filters.currency) || "THB";
    }

    get unitLabel() {
        const name = this.currencyName;
        return this.unit === "mb" ? `${name} (million)` : name;
    }

    openList(name, resModel, domain) {
        const filters = this.echoFilters;
        const companyIds = filters.company_id ? [filters.company_id]
            : (filters.companies || []).map((company) => company.id);
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: resModel,
            view_mode: "tree,form",
            views: [[false, "list"], [false, "form"]],
            domain,
            context: companyIds.length ? { allowed_company_ids: companyIds } : {},
            target: "current",
        });
    }

    // ---------------- drill-down helpers ----------------
    // ทุกตัวเลขบน dashboard ต้องกดลงไปดูเอกสารจริงได้ — helper กลุ่มนี้
    // ประกอบโดเมนจาก filters ที่ engine echo กลับมา (ไม่มีตัวเลขจาก client)

    get echoFilters() {
        return (this.props.data || this.state?.data || {}).filters || {};
    }

    /** ขอบเขตบริษัทชุดเดียวกับยอดรวมที่ engine ส่งมา */
    companyDomain(field = "company_id") {
        const companyId = this.echoFilters.company_id;
        const ids = companyId ? [companyId]
            : (this.echoFilters.companies || []).map((company) => company.id);
        return ids.length ? [[field, "in", ids]] : [];
    }

    /** เลื่อนวันที่ "YYYY-MM-DD" ไป ±N วัน (ใช้ทำถัง aging/committed) */
    dateOffset(baseStr, days) {
        const base = new Date(`${baseStr}T00:00:00`);
        base.setDate(base.getDate() + days);
        const mm = `${base.getMonth() + 1}`.padStart(2, "0");
        const dd = `${base.getDate()}`.padStart(2, "0");
        return `${base.getFullYear()}-${mm}-${dd}`;
    }

    /** วันเริ่มปีงบจริงของบริษัทที่ engine ใช้คำนวณยอด */
    get fyFrom() {
        return this.echoFilters.fy_start || `${this.echoFilters.year}-01-01`;
    }

    get fyTo() {
        return this.echoFilters.as_of;
    }

    /** ใบแจ้งหนี้/บิล posted ช่วงปีงบ (types เช่น ["out_invoice","out_refund"]) */
    openMoves(name, types, extraDomain = []) {
        this.openList(name, "account.move", [
            ["move_type", "in", types],
            ["state", "=", "posted"],
            ["invoice_date", ">=", this.fyFrom],
            ["invoice_date", "<=", this.fyTo],
            ...this.companyDomain(),
            ...extraDomain,
        ]);
    }

    /** ลูกหนี้/เจ้าหนี้คงค้าง ครบกำหนดในช่วงวันที่ (สำหรับกดช่องรายสัปดาห์) */
    openOpenMovesDue(name, types, dateFrom, dateTo) {
        const domain = [
            ["move_type", "in", types],
            ["state", "=", "posted"],
            ["payment_state", "in", ["not_paid", "partial"]],
            ...this.companyDomain(),
        ];
        if (dateFrom) {
            domain.push(["invoice_date_due", ">=", dateFrom]);
        }
        if (dateTo) {
            domain.push(["invoice_date_due", "<=", dateTo]);
        }
        this.openList(name, "account.move", domain);
    }

    /** รายการบัญชีแยกตามประเภทบัญชี (เงินสด/รายได้ ฯลฯ) ช่วงปีงบ */
    openJournalItems(name, accountTypes, cumulative = false) {
        const domain = [
            ["account_id.account_type", "in", accountTypes],
            ["parent_state", "=", "posted"],
            ["date", "<=", this.fyTo],
            ...this.companyDomain(),
        ];
        if (!cumulative) {
            domain.push(["date", ">=", this.fyFrom]);
        }
        this.openList(name, "account.move.line", domain);
    }

    openForm(resModel, resId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: resId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }

    /**
     * ช่องตารางเทียบหลายงวด (แถวหนึ่ง × คอลัมน์หนึ่ง) → journal items ในหน้าต่าง
     * วันที่ของคอลัมน์นั้น  ใช้ทั้งแท็บ Compare (BI) และงบ waterfall ในแท็บ
     * Statements  รองรับ drill 3 แบบ: ตามประเภทบัญชี (types), ตาม id ที่ระบุ
     * (account_ids) และ id ที่ต้องกันออก (exclude_ids — บรรทัด SG&A ที่เป็นตัวปิด)
     * แถวที่ผูกมิติเพิ่ม (แท็บช่องทางขาย) ส่ง `extra_domain` มาต่อท้ายได้
     */
    openCmpCell(row, col) {
        if (!col) {
            return;
        }
        const ids = row.account_ids || [];
        const types = row.types || [];
        const exclude = row.exclude_ids || [];
        if (!ids.length && !types.length) {
            return;
        }
        const domain = [
            ["parent_state", "=", "posted"],
            ["date", "<=", row.cumulative ? col.as_of : col.date_to],
            ...this.companyDomain(),
        ];
        if (!row.cumulative) {
            domain.push(["date", ">=", col.date_from]);
        }
        if (ids.length) {
            domain.push(["account_id", "in", ids]);
        }
        if (types.length) {
            domain.push(["account_id.account_type", "in", types]);
        }
        if (exclude.length) {
            domain.push(["account_id", "not in", exclude]);
        }
        if (row.extra_domain) {
            domain.push(...row.extra_domain);
        }
        this.openList(
            `${row.label} · ${col.label}`, "account.move.line", domain);
    }
}

Object.assign(BsfTab.prototype, ZoomMixin);
