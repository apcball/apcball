/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * ตัวสลับแกนการจัดกลุ่ม — คลัง→สินค้า หรือ สินค้า→คลัง พร้อมระดับเสริม
 *
 * component นี้ไม่ถือ state เอง ทุกการเปลี่ยนแปลงส่งกลับผ่าน onChange เพื่อให้
 * server เป็นผู้ normalize ลำดับระดับที่แท้จริง แล้วส่งกลับมาใน data.levels
 */
export class ScAxisToggle extends Component {
    static template = "biz_st_stock_card.ScAxisToggle";
    static props = {
        options: Object,
        levels: { type: Array, optional: true },
        onChange: Function,
    };
    static defaultProps = { levels: [] };

    get axes() {
        return [
            { id: "wh_product", label: "คลัง → สินค้า" },
            { id: "product_wh", label: "สินค้า → คลัง" },
        ];
    }

    get extraLevels() {
        return [
            { field: "group_categ", label: "หมวดสินค้า" },
            { field: "group_location", label: "ที่เก็บย่อย" },
            { field: "group_lot", label: "ล็อต/ซีเรียล" },
        ];
    }

    /** เส้นทางระดับที่ได้จริง — มาจาก server ไม่ใช่คำนวณซ้ำบน client */
    get breadcrumb() {
        return this.props.levels.map((level) => level.label).join(" → ");
    }

    setAxis(axis) {
        if (axis !== this.props.options.group_mode) {
            this.props.onChange({ group_mode: axis });
        }
    }

    toggle(field) {
        this.props.onChange({ [field]: !this.props.options[field] });
    }
}
