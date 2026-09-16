/** @odoo-module **/

import { useState } from "@odoo/owl";
import { AGING_COLORS, BsfTab, CMP_MODES, CMP_COUNTS, buildStackedBar } from "./bsf_widgets";
import { BsfAiCard } from "./bsf_ai_card";

/**
 * Financial Statements (สไตล์ SAP F.01) — P&L (waterfall) / Balance Sheet
 * (waterfall แยกหมุนเวียน/ไม่หมุนเวียน) / Cash Flow / AR aging
 *
 * ทั้ง P&L และงบดุลเป็น waterfall: บรรทัด "line" กางรายบัญชี/drill ได้
 * บรรทัด "total"/"subtotal" เป็นบรรทัดสรุป
 *
 * ตัวเลือก "เทียบเป็น เดือน/ไตรมาส/ปี × 2–6 ช่วง" (บนการ์ด P&L และงบดุล) ยิงตัวกรอง
 * compare_mode/compare_count ชุดเดียวกับแท็บ Compare (BI) — เปิดที่นี่แล้วแท็บ
 * Compare ก็เทียบช่วงเดียวกัน  เมื่อเปิดโหมดเทียบ งบจะแตกเป็นหลายคอลัมน์จาก
 * payload ของ slice `compare` (คอลัมน์ขวาสุด = งวดที่เลือกใน toolbar)
 */
export class BsfTabStatements extends BsfTab {
    static template = "biz_smart_finance.TabStatements";
    static components = { BsfAiCard };
    static props = { data: Object, unit: String, onCompare: Function };

    setup() {
        super.setup();
        // เริ่มหุบทุกกลุ่มแบบ F.01 — จำสถานะเฉพาะระหว่างเปิดแท็บ
        this.ui = useState({ open: {} });
        this.cmpModes = CMP_MODES;
        this.cmpCounts = CMP_COUNTS;
    }

    get st() {
        return this.props.data.statements;
    }

    get cmp() {
        return this.props.data.compare || {};
    }

    /** เปิดโหมดเทียบหลายงวดอยู่หรือไม่ (มีคอลัมน์พร้อมแสดง) */
    get cmpActive() {
        return Boolean(this.cmp.enabled && (this.cmp.columns || []).length);
    }

    get cmpMode() {
        return this.cmp.mode || "month";
    }

    get cmpCount() {
        return this.cmp.count || 4;
    }

    get cmpColumns() {
        return this.cmp.columns || [];
    }

    /** แถวของงบ P&L — โหมดเทียบใช้แถว waterfall จาก slice compare */
    get pnlRows() {
        return (this.cmpActive ? this.cmp.pnl_rows : this.st.pnl.rows) || [];
    }

    /** แถวของงบแสดงฐานะการเงิน — โหมดเทียบใช้จาก slice compare */
    get bsRows() {
        return (this.cmpActive
            ? this.cmp.bs_rows
            : this.st.balance_sheet.rows) || [];
    }

    /** แถวของงบกระแสเงินสด — โหมดเทียบใช้จาก slice compare */
    get cfRows() {
        return (this.cmpActive
            ? this.cmp.cf_rows
            : this.st.cashflow.rows) || [];
    }

    /** ทิศทางที่ "ดี" ของแถว: รายได้/สินทรัพย์/ทุน/บรรทัดสรุป = ขึ้นดี
     *  ต้นทุน ค่าใช้จ่าย หนี้สิน = ขึ้นแย่ (ใช้กลับสีลูกศร Δ%) */
    goodWhenUp(row) {
        if (typeof row.good_when_up === "boolean") {
            return row.good_when_up;
        }
        // งบกระแสเงินสด: ตัวเลขบวก = เงินเข้า = ดีเสมอ
        if (row.sec === "cfo" || row.sec === "cfi"
            || row.sec === "cff" || row.sec === "net") {
            return true;
        }
        if (row.kind !== "line") {
            return true;
        }
        const badUp = ["cogs", "sga", "depreciation", "interest", "tax"];
        if (badUp.includes(row.key)) {
            return false;
        }
        return !(row.sec === "cl" || row.sec === "ncl");
    }

    isOpen(key) {
        return !!this.ui.open[key];
    }

    toggle(key) {
        this.ui.open[key] = !this.ui.open[key];
    }

    // ---------------- ตัวเลือกช่วงเทียบ (ยิง server ใหม่, ใช้ร่วมทั้ง 2 การ์ด) ----
    onCmpModeChange(ev) {
        this.props.onCompare(ev.target.value, this.cmpCount);
    }

    onCmpCountChange(ev) {
        this.props.onCompare(this.cmpMode, parseInt(ev.target.value, 10));
    }

    /** ปิดโหมดเทียบ กลับไปงบ 2 คอลัมน์ (งวดนี้ / งวดก่อน) */
    closeCmpCompare() {
        this.props.onCompare("", this.cmpCount);
    }

    get agingBuckets() {
        const b = this.st.ar_aging.buckets;
        return [
            { code: "current", label: "Current", amount: b.current },
            { code: "b1_30", label: "1 - 30 days", amount: b.b1_30 },
            { code: "b31_60", label: "31 - 60 days", amount: b.b31_60 },
            { code: "b60_plus", label: "> 60 days", amount: b.b60_plus },
        ];
    }

    get agingBar() {
        return buildStackedBar(
            this.agingBuckets.map((seg) => seg.amount), AGING_COLORS,
        ).map((seg, index) => ({ ...seg, ...this.agingBuckets[index] }));
    }

    // ---------------- drill-downs ----------------
    /** แถวรายบัญชี → journal items ของบัญชีนั้น (BS = สะสมถึง as_of)
     * บัญชีภายนอก (id ติดลบ, drillable === false) ไม่มีเอกสารต้นทางใน Odoo */
    openAccount(row, cumulative) {
        if (row.drillable === false) {
            return;
        }
        const domain = [
            ["account_id", "=", row.account_id],
            ["parent_state", "=", "posted"],
            ["date", "<=", this.fyTo],
            ...this.companyDomain(),
        ];
        if (!cumulative) {
            domain.push(["date", ">=", this.fyFrom]);
        }
        this.openList(`${row.code} ${row.label}`, "account.move.line", domain);
    }

    /** แถวงบกระแสเงินสด → journal items ตามประเภทบัญชี */
    openGroup(row, cumulative) {
        if (row.types && row.types.length) {
            this.openJournalItems(row.label, row.types, cumulative);
        }
    }

    /** บรรทัด line ของงบ (โหมด 2 คอลัมน์) → journal items
     *  P&L: ช่วงปีงบถึง as-of · งบดุล (cumulative=true): ยอดสะสมถึง as-of
     *  รองรับ drill ตามประเภทบัญชี, ตาม id ที่ผูกไว้ และ id ที่ต้องกันออก */
    openStmtLine(row, cumulative) {
        const types = row.types || [];
        const ids = row.account_ids || [];
        const exclude = row.exclude_ids || [];
        if (!types.length && !ids.length) {
            return;
        }
        const domain = [
            ["parent_state", "=", "posted"],
            ["date", "<=", this.fyTo],
            ...this.companyDomain(),
        ];
        if (!cumulative) {
            domain.push(["date", ">=", this.fyFrom]);
        }
        if (types.length) {
            domain.push(["account_id.account_type", "in", types]);
        }
        if (ids.length) {
            domain.push(["account_id", "in", ids]);
        }
        if (exclude.length) {
            domain.push(["account_id", "not in", exclude]);
        }
        this.openList(row.label, "account.move.line", domain);
    }

    /** ช่องหนึ่ง (แถว × คอลัมน์) ในโหมดเทียบ → รายการบัญชีในหน้าต่างคอลัมน์นั้น */
    openStmtCell(row, colIndex) {
        this.openCmpCell(row, this.cmpColumns[colIndex]);
    }

    /** ถัง AR aging → ใบแจ้งหนี้ค้างรับช่วงอายุนั้น (นับจากวันนี้ เหมือน AP) */
    openArBucket(seg) {
        const today = this.echoFilters.today;
        const ranges = {
            current: [today, false],
            b1_30: [this.dateOffset(today, -30), this.dateOffset(today, -1)],
            b31_60: [this.dateOffset(today, -60), this.dateOffset(today, -31)],
            b60_plus: [false, this.dateOffset(today, -61)],
        };
        const range = ranges[seg.code] || [false, false];
        this.openOpenMovesDue(
            `ลูกหนี้ค้างรับ · ${seg.label}`, ["out_invoice"],
            range[0], range[1]);
    }

    openCustomer(row) {
        if (!row.partner_id) {
            return;
        }
        this.openList(row.name, "account.move", [
            ["move_type", "in", ["out_invoice", "out_refund"]],
            ["state", "=", "posted"],
            ["payment_state", "in", ["not_paid", "partial"]],
            ["partner_id", "=", row.partner_id],
            ...this.companyDomain(),
        ]);
    }
}
