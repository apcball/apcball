/** @odoo-module **/

import { Component, useExternalListener, useState } from "@odoo/owl";
import { ScAxisToggle } from "@biz_st_stock_card/stock_card/sc_axis_toggle";
import { DATE_PRESETS, presetRange } from "@biz_st_stock_card/stock_card/sc_shared";

/**
 * แถบตัวกรอง
 *
 * component นี้ไม่ถือ state ของตัวกรองเลย ทุกการเปลี่ยนแปลงส่งกลับผ่าน onChange
 * แล้วรอค่าที่ server normalize กลับมา — ตัวกรองบนจอกับตัวกรองในไฟล์ที่พิมพ์จึง
 * เป็นชุดเดียวกันเสมอ
 */
export class ScFilterBar extends Component {
    static template = "biz_st_stock_card.ScFilterBar";
    static components = { ScAxisToggle };
    static props = {
        options: Object,
        companies: { type: Array, optional: true },
        warehouses: { type: Array, optional: true },
        pickingTypes: { type: Array, optional: true },
        levels: { type: Array, optional: true },
        loading: { type: Boolean, optional: true },
        onChange: Function,
        onRefresh: Function,
        onPrint: Function,
        onUnfoldAll: Function,
        onFoldAll: Function,
    };
    static defaultProps = { companies: [], warehouses: [], pickingTypes: [], levels: [] };

    setup() {
        this.state = useState({ companyMenuOpen: false, whMenuOpen: false });
        useExternalListener(window, "click", () => {
            this.state.companyMenuOpen = false;
            this.state.whMenuOpen = false;
        });
    }

    // --- generic handlers -------------------------------------------
    onDateChange(field, ev) {
        if (ev.target.value) {
            this.props.onChange({ [field]: ev.target.value });
        }
    }

    onSelectChange(field, ev) {
        this.props.onChange({ [field]: ev.target.value });
    }

    onPickingTypeChange(ev) {
        const value = ev.target.value;
        this.props.onChange({ picking_type_ids: value === "0" ? [] : [parseInt(value)] });
    }

    toggle(field) {
        this.props.onChange({ [field]: !this.props.options[field] });
    }

    // --- date presets ----------------------------------------------
    get presets() {
        return DATE_PRESETS;
    }

    applyPreset(presetId) {
        this.props.onChange(presetRange(presetId));
    }

    // --- multi-select pickers --------------------------------------
    get companyLabel() {
        const ids = this.props.options.company_ids || [];
        if (ids.length === 1) {
            const found = this.props.companies.find((c) => c.id === ids[0]);
            return found ? found.name : "1 บริษัท";
        }
        return `${ids.length} บริษัท`;
    }

    get warehouseLabel() {
        const ids = this.props.options.warehouse_ids || [];
        if (ids.length === 1) {
            const found = this.props.warehouses.find((w) => w.id === ids[0]);
            return found ? found.name : "1 คลัง";
        }
        if (ids.length > 1) {
            return `${ids.length} คลัง`;
        }
        return this.props.options.all_warehouses ? "ทุกคลัง" : "เลือกคลัง";
    }

    chooseAllWarehouses() {
        this.props.onChange({ warehouse_ids: [], all_warehouses: true });
    }

    isPicked(field, id) {
        return (this.props.options[field] || []).includes(id);
    }

    togglePicked(field, id) {
        const current = this.props.options[field] || [];
        const next = current.includes(id)
            ? current.filter((item) => item !== id)
            : current.concat([id]);
        // เหลือศูนย์บริษัทแล้วรายงานจะว่างเปล่าโดยไม่มีคำอธิบาย — กันไว้ตรงนี้
        if (field === "company_ids" && !next.length) {
            return;
        }
        const changes = { [field]: next };
        // เลือกคลังเจาะจงแล้ว ต้องเลิกโหมด "ทุกคลัง" เดิม ไม่งั้นตัวกรองขัดกันเอง
        if (field === "warehouse_ids") {
            changes.all_warehouses = false;
        }
        this.props.onChange(changes);
    }
}
