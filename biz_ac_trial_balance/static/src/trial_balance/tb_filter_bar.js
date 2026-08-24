/** @odoo-module **/

import { Component, useExternalListener, useState } from "@odoo/owl";

/**
 * แถบตัวกรองของงบทดลอง — เรียงตามรูปแบบที่นักบัญชีคุ้นเคย:
 * แสดงข้อมูล (ก่อน/หลังปิดบัญชี) → ช่วงเวลา → บริษัท → แยกหมวดบัญชี → พิมพ์รายงาน → รีเฟรช
 *
 * component นี้ไม่ถือ state เอง ทุกการเปลี่ยนแปลงส่งกลับผ่าน onChange ให้ตัวแม่
 * เป็นคนตัดสินใจโหลดใหม่ — ป้องกันไม่ให้ตัวกรองบนจอกับ options ที่ส่งไปพิมพ์เพี้ยนกัน
 */
export class TbFilterBar extends Component {
    static template = "biz_ac_trial_balance.TbFilterBar";
    static props = {
        options: Object,
        companies: { type: Array, optional: true },
        loading: { type: Boolean, optional: true },
        onChange: Function,
        onRefresh: Function,
        onPrint: Function,
    };
    static defaultProps = { companies: [] };

    setup() {
        this.state = useState({ companyMenuOpen: false });
        // dropdown ทำเองในโมดูลนี้ ไม่พึ่ง component ของ core — คลิกที่อื่นแล้วปิด
        // ปุ่มเปิดเมนูกับตัวเมนูใช้ .stop กันคลิกไม่ให้วิ่งมาถึง listener ตัวนี้
        useExternalListener(window, "click", () => {
            this.state.companyMenuOpen = false;
        });
    }

    // ---- ช่องเลือกบริษัท ------------------------------------------------
    /** โผล่เฉพาะตอนที่ผู้ใช้มีสิทธิ์มากกว่าหนึ่งบริษัท */
    get hasCompanyChoice() {
        return this.props.companies.length > 1;
    }

    get selectedCompanyIds() {
        return this.props.options.company_ids || [];
    }

    isCompanySelected(companyId) {
        return this.selectedCompanyIds.includes(companyId);
    }

    get companyLabel() {
        const selected = this.props.companies.filter((c) => this.isCompanySelected(c.id));
        if (!selected.length) {
            return "บริษัท";
        }
        return selected.length === 1 ? selected[0].name : `${selected.length} บริษัท`;
    }

    toggleCompanyMenu() {
        this.state.companyMenuOpen = !this.state.companyMenuOpen;
    }

    toggleCompany(companyId) {
        const selected = new Set(this.selectedCompanyIds);
        if (selected.has(companyId)) {
            // ต้องเหลืออย่างน้อยหนึ่งบริษัทเสมอ ไม่งั้นเซิร์ฟเวอร์จะถอยไปใช้ค่าตั้งต้น
            // แล้วผู้ใช้จะงงว่าทำไมติ๊กออกหมดแล้วข้อมูลไม่หาย
            if (selected.size === 1) {
                return;
            }
            selected.delete(companyId);
        } else {
            selected.add(companyId);
        }
        // คงลำดับตามรายชื่อที่เซิร์ฟเวอร์ส่งมา หัวรายงานจะได้ไม่สลับไปมา
        this.props.onChange({
            company_ids: this.props.companies
                .map((c) => c.id)
                .filter((id) => selected.has(id)),
        });
    }

    get presets() {
        return [
            { id: "this_month", label: "เดือนนี้" },
            { id: "last_month", label: "เดือนก่อน" },
            { id: "this_quarter", label: "ไตรมาสนี้" },
            { id: "fiscal_year", label: "ปีบัญชีนี้" },
        ];
    }

    /** แปลง preset เป็นคู่วันที่ — ใช้เวลาท้องถิ่นให้ตรงกับที่ผู้ใช้เห็นบนปฏิทิน */
    applyPreset(presetId) {
        const today = new Date();
        let from;
        let to;
        if (presetId === "this_month") {
            from = new Date(today.getFullYear(), today.getMonth(), 1);
            to = new Date(today.getFullYear(), today.getMonth() + 1, 0);
        } else if (presetId === "last_month") {
            from = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            to = new Date(today.getFullYear(), today.getMonth(), 0);
        } else if (presetId === "this_quarter") {
            const q = Math.floor(today.getMonth() / 3);
            from = new Date(today.getFullYear(), q * 3, 1);
            to = new Date(today.getFullYear(), q * 3 + 3, 0);
        } else {
            // ปีบัญชีจริงมาจากเซิร์ฟเวอร์ (อาจไม่ตรงปีปฏิทิน) ใช้ค่าที่ normalize มาแล้ว
            this.props.onChange({
                date_from: this.props.options.fy_date_from,
                date_to: this.props.options.fy_date_to,
            });
            return;
        }
        this.props.onChange({ date_from: isoDate(from), date_to: isoDate(to) });
    }

    onDateChange(field, ev) {
        if (ev.target.value) {
            this.props.onChange({ [field]: ev.target.value });
        }
    }

    onSelectChange(field, ev) {
        this.props.onChange({ [field]: ev.target.value });
    }

    /** ปุ่มรวม/แยกบริษัทโผล่เฉพาะตอนที่รายงานครอบมากกว่าหนึ่งบริษัท */
    get isMultiCompany() {
        return (this.props.options.company_ids || []).length > 1;
    }

    toggleCompanyMode() {
        this.props.onChange({
            company_mode:
                this.props.options.company_mode === "split" ? "consolidated" : "split",
        });
    }

    toggle(field) {
        this.props.onChange({ [field]: !this.props.options[field] });
    }
}

function isoDate(date) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
