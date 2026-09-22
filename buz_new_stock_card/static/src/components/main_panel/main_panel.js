/** @odoo-module **/

import { Component } from "@odoo/owl";

export class MainPanel extends Component {
    static template = "buz_new_stock_card.MainPanel";
    static props = [
        "state", "onRetry", "onChangePage", "onChangePageSize", "openDocument",
    ];

    fmt(n) {
        return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0);
    }

    get uom() { return this.props.state.product?.uom_id?.[1] || "—"; }

    get isMulti() { return this.props.state.cardData?.mode === "multi"; }

    lineLocation(line) {
        if (!this.isMulti) { return line.location_name; }
        return line.to_location || line.from_location || line.location_label || "—";
    }

    get productType() {
        return { product: "สินค้าจัดเก็บสต๊อก", consu: "สินค้าอุปโภคบริโภค", service: "บริการ" }[this.props.state.product?.type] || "—";
    }

    get summaryCards() {
        const data = this.props.state.cardData;
        const cards = [
            { key: "opening", label: "ยอดยกมา", icon: "fa-clone", value: data.opening_balance, valueBaht: data.opening_value },
            { key: "in", label: "รับทั้งหมด", icon: "fa-sign-in", value: data.total_in, valueBaht: data.total_in_value },
            { key: "out", label: "จ่ายทั้งหมด", icon: "fa-sign-out", value: data.total_out, valueBaht: data.total_out_value },
            { key: "balance", label: "คงเหลือ", icon: "fa-cube", value: data.closing_balance, valueBaht: data.closing_value },
        ];
        if (!data.can_see_value) {
            cards.forEach((card) => delete card.valueBaht);
        }
        return cards;
    }

    get pages() {
        const start = Math.max(0, Math.min(this.props.state.page - 2, this.lastPage - 4));
        return Array.from({ length: Math.min(5, this.lastPage + 1) }, (_, index) => start + index);
    }

    onDocClick(line) {
        if (line.res_model && line.res_id) {
            this.props.openDocument(line.res_model, line.res_id);
        }
    }

    get pageStart() {
        if (!this.props.state.cardData || !this.props.state.cardData.total_count) {
            return 0;
        }
        return this.props.state.page * this.props.state.pageSize + 1;
    }

    get pageEnd() {
        const d = this.props.state.cardData;
        if (!d || !d.total_count) {
            return 0;
        }
        return Math.min(this.pageStart + d.lines.length - 1, d.total_count);
    }

    onPageSizeChange(ev) {
        this.props.onChangePageSize(parseInt(ev.target.value, 10));
    }

    get lastPage() {
        const d = this.props.state.cardData;
        if (!d || !d.page_size) {
            return 0;
        }
        return Math.max(0, Math.ceil(d.total_count / d.page_size) - 1);
    }
}
