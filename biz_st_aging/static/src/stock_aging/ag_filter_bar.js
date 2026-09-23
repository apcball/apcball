/** @odoo-module **/

import { Component, useExternalListener, useState } from "@odoo/owl";

/**
 * แถบตัวกรองของรายงานอายุสินค้าคงเหลือ
 *
 * component นี้ไม่ถือ state ของตัวกรองเลย (ยกเว้นข้อความในช่องค้นหาที่ยังไม่กด Enter)
 * ทุกการเปลี่ยนแปลงส่งกลับผ่าน onChange แล้วรอค่าที่ server normalize กลับมา
 */
export class AgFilterBar extends Component {
    static template = "biz_st_aging.AgFilterBar";
    static props = {
        options: Object,
        companies: { type: Array, optional: true },
        warehouses: { type: Array, optional: true },
        categories: { type: Array, optional: true },
        levels: { type: Array, optional: true },
        loading: { type: Boolean, optional: true },
        onChange: Function,
        onRefresh: Function,
        onReset: Function,
        onPrint: Function,
        onOpenConfig: Function,
        onUnfoldAll: Function,
        onFoldAll: Function,
    };
    static defaultProps = { companies: [], warehouses: [], categories: [], levels: [] };

    setup() {
        this.state = useState({
            companyMenuOpen: false,
            whMenuOpen: false,
            search: this.props.options.product_search || "",
        });
        useExternalListener(window, "click", () => {
            this.state.companyMenuOpen = false;
            this.state.whMenuOpen = false;
        });
    }

    get axes() {
        return [
            { id: "wh_product", label: "คลัง → สินค้า" },
            { id: "product_wh", label: "สินค้า → คลัง" },
        ];
    }

    get extraLevels() {
        return [
            { field: "group_categ", label: "แสดงหมวดสินค้า" },
            { field: "group_lot", label: "แสดง Lot/Serial" },
            { field: "group_location", label: "แสดงที่เก็บย่อย" },
        ];
    }

    get breadcrumb() {
        return this.props.levels.map((level) => level.label).join(" → ");
    }

    // --- generic handlers -------------------------------------------
    onDateChange(ev) {
        if (ev.target.value) {
            this.props.onChange({ date_to: ev.target.value });
        }
    }

    onSelectChange(field, ev) {
        this.props.onChange({ [field]: ev.target.value });
    }

    onCategChange(ev) {
        const value = parseInt(ev.target.value, 10);
        this.props.onChange({ categ_ids: value ? [value] : [] });
    }

    toggle(field) {
        this.props.onChange({ [field]: !this.props.options[field] });
    }

    setAxis(axis) {
        if (axis !== this.props.options.group_mode) {
            this.props.onChange({ group_mode: axis });
        }
    }

    // --- product search --------------------------------------------
    onSearchInput(ev) {
        this.state.search = ev.target.value;
    }

    onSearchKey(ev) {
        if (ev.key === "Enter") {
            this.applySearch();
        }
    }

    applySearch() {
        const text = (this.state.search || "").trim();
        if (text !== (this.props.options.product_search || "")) {
            this.props.onChange({ product_search: text });
        }
    }

    clearSearch() {
        this.state.search = "";
        if (this.props.options.product_search) {
            this.props.onChange({ product_search: "" });
        }
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
        if (!ids.length) {
            return "ทุกคลัง";
        }
        if (ids.length === 1) {
            const found = this.props.warehouses.find((w) => w.id === ids[0]);
            return found ? found.name : "1 คลัง";
        }
        return `${ids.length} คลัง`;
    }

    get categValue() {
        const ids = this.props.options.categ_ids || [];
        return ids.length ? String(ids[0]) : "0";
    }

    /** เทียบเป็นสตริงนอกเทมเพลต — QWeb เรียก global อย่าง String()/parseInt() ไม่ได้ (ctx.String is not a function) */
    isCategSelected(categId) {
        return this.categValue === String(categId);
    }

    isPicked(field, id) {
        return (this.props.options[field] || []).includes(id);
    }

    togglePicked(field, id) {
        const current = this.props.options[field] || [];
        const next = current.includes(id)
            ? current.filter((item) => item !== id)
            : current.concat([id]);
        if (field === "company_ids" && !next.length) {
            return;
        }
        this.props.onChange({ [field]: next });
    }
}
