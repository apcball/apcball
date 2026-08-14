/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

const MO_SORT_KEYS = {
    mo_name: (mo) => mo.mo_name,
    mo_date: (mo) => mo.mo_date,
    subtotal_qty: (mo) => mo.subtotal_qty,
    subtotal_amount: (mo) => mo.subtotal_amount,
};

const MATERIAL_SORT_KEYS = {
    product_code: (m) => m.product_code,
    quantity: (m) => m.quantity,
    unit_cost: (m) => m.unit_cost,
    amount: (m) => m.amount,
};

export class WipMainPanel extends Component {
    static template = "buz_wip_manufacturing_report.WipMainPanel";
    static props = [
        "state", "onSetSearch", "onChangePage", "onChangePageSize",
        "toggleExpand", "expandAll", "collapseAll", "openRecord",
    ];

    setup() {
        this.local = useState({ sortKey: "mo_date", sortDir: "desc" });
    }

    fmt(n) {
        return (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    onSearchInput(ev) {
        this.props.onSetSearch(ev.target.value);
    }

    onSort(key) {
        if (this.local.sortKey === key) {
            this.local.sortDir = this.local.sortDir === "asc" ? "desc" : "asc";
        } else {
            this.local.sortKey = key;
            this.local.sortDir = "asc";
        }
    }

    onPageSizeChange(ev) {
        this.props.onChangePageSize(parseInt(ev.target.value, 10));
    }

    get pageStart() {
        const d = this.props.state.reportData;
        if (!d || !d.total_count) return 0;
        return this.props.state.page * this.props.state.pageSize + 1;
    }

    get pageEnd() {
        const d = this.props.state.reportData;
        if (!d) return 0;
        return Math.min(this.pageStart + d.data.length - 1, d.total_count);
    }

    get lastPage() {
        const d = this.props.state.reportData;
        if (!d || !this.props.state.pageSize) return 0;
        return Math.max(0, Math.ceil(d.total_count / this.props.state.pageSize) - 1);
    }

    /** Page numbers to render, with "..." gaps for large page counts
     * (e.g. [0,1,2,'...',6] for a 7-page set on page 0). */
    get pageNumbers() {
        const last = this.lastPage;
        const current = this.props.state.page;
        if (last <= 6) {
            return Array.from({ length: last + 1 }, (_, i) => i);
        }
        const pages = new Set([0, 1, 2, last - 1, last, current, current - 1, current + 1]);
        const sorted = [...pages].filter((p) => p >= 0 && p <= last).sort((a, b) => a - b);
        const result = [];
        let prev = null;
        for (const p of sorted) {
            if (prev !== null && p - prev > 1) {
                result.push("...");
            }
            result.push(p);
            prev = p;
        }
        return result;
    }

    _matchesSearch(mo, material, term) {
        const haystacks = [
            mo.mo_name, material.product_code, material.product_name, material.location_name,
        ];
        return haystacks.some((h) => (h || "").toLowerCase().includes(term));
    }

    /** MO -> Material rows, filtered by client-side search and sorted
     * without breaking the MO grouping (sort applies within each MO's
     * material list, and reorders MOs by the same key when it's a mo-level
     * key). */
    get visibleMos() {
        const d = this.props.state.reportData;
        if (!d) return [];
        const term = (this.props.state.search || "").trim().toLowerCase();

        let mos = d.data.map((mo) => {
            let materials = mo.materials;
            if (term) {
                materials = materials.filter((m) => this._matchesSearch(mo, m, term));
            }
            return { ...mo, materials };
        });

        if (term) {
            mos = mos.filter((mo) => mo.mo_name.toLowerCase().includes(term) || mo.materials.length);
        }

        const matGetter = MATERIAL_SORT_KEYS[this.local.sortKey];
        if (matGetter) {
            for (const mo of mos) {
                mo.materials = [...mo.materials].sort((a, b) => {
                    const av = matGetter(a), bv = matGetter(b);
                    const cmp = av > bv ? 1 : av < bv ? -1 : 0;
                    return this.local.sortDir === "asc" ? cmp : -cmp;
                });
            }
        }

        const moGetter = MO_SORT_KEYS[this.local.sortKey];
        if (moGetter) {
            mos = [...mos].sort((a, b) => {
                const av = moGetter(a), bv = moGetter(b);
                const cmp = av > bv ? 1 : av < bv ? -1 : 0;
                return this.local.sortDir === "asc" ? cmp : -cmp;
            });
        }

        return mos;
    }

    isExpanded(moId) {
        return !!this.props.state.expanded[moId];
    }
}
