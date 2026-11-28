/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/webclient/actions/action_hook";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const TARGET = "buz.sales.target";
const IMPORT = "buz.sales.target.import";
const MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];
const NUMBER = new Intl.NumberFormat("th-TH", { maximumFractionDigits: 2 });
const MAX_BYTES = 5 * 1024 * 1024;

export class SalesTargetBoard extends Component {
    static template = "buz_sales_dashboard.Targets";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        const today = new Date();
        this.state = useState({
            month: this.isoMonth(today.getFullYear(), today.getMonth()),
            board: null,
            // row key -> the text typed in its cell
            edits: {},
            closed: {},
            saving: false,
            file: this.emptyFile(),
            dragging: false,
        });
        useSetupAction({
            beforeLeave: () => this.confirmDiscard(),
            beforeUnload: (ev) => {
                if (this.dirty.length) {
                    ev.preventDefault();
                    ev.returnValue = "";
                }
            },
        });
        onWillStart(() => this.load());
    }

    emptyFile() {
        return { name: "", data: "", preview: null, busy: false };
    }

    isoMonth(year, index) {
        const date = new Date(Date.UTC(year, index, 1));
        return date.toISOString().slice(0, 10);
    }

    async load() {
        this.state.board = await this.orm.call(TARGET, "get_board", [this.state.month]);
        this.state.edits = {};
    }

    // ---------------------------------------------------------------- rows
    get rows() {
        const rows = [];
        for (const team of this.state.board.teams) {
            rows.push(team, ...team.members);
        }
        return [...rows, ...this.state.board.others];
    }

    /** The cell's value: a number, false when not set, null when unreadable. */
    value(row) {
        if (!(row.key in this.state.edits)) {
            return row.target;
        }
        const text = this.state.edits[row.key].replace(/[,\s]/g, "");
        if (!text) {
            return false;
        }
        return /^(\d+(\.\d*)?|\.\d+)$/.test(text) && Number(text) < 1e13 ? Number(text) : null;
    }

    text(row) {
        if (row.key in this.state.edits) {
            return this.state.edits[row.key];
        }
        return row.target === false ? "" : NUMBER.format(row.target);
    }

    isChanged(row) {
        return row.key in this.state.edits && this.value(row) !== row.target;
    }

    get dirty() {
        return this.state.board ? this.rows.filter((row) => this.isChanged(row)) : [];
    }

    get invalid() {
        return this.dirty.filter((row) => this.value(row) === null);
    }

    get notSet() {
        return this.rows.filter((row) => row.editable && this.value(row) === false).length;
    }

    onInput(row, ev) {
        this.state.edits[row.key] = ev.target.value;
    }

    onBlur(row) {
        if (!this.isChanged(row)) {
            delete this.state.edits[row.key];
        }
    }

    status(row) {
        const value = this.value(row);
        if (value === null) {
            return { css: "o_bsd_bad", label: "ตัวเลขไม่ถูกต้อง" };
        }
        if (row.level === "team" && value !== false) {
            const people = row.members.map((m) => this.value(m)).filter((v) => typeof v === "number");
            if (people.length) {
                const sum = people.reduce((a, b) => a + b, 0);
                const gap = Math.abs(sum - value);
                return gap < 0.005
                    ? { css: "o_bsd_done", label: "ตรงกับรายคน" }
                    : { css: "o_bsd_behind", label: `รายคนรวม ${this.amount(sum)} · ต่าง ${this.amount(gap)}` };
            }
        }
        if (this.isChanged(row)) {
            return { css: "o_bsd_ahead", label: "แก้ไขยังไม่บันทึก" };
        }
        return value === false ? { css: "o_bsd_none", label: "ยังไม่ตั้งเป้า" } : null;
    }

    amount(value) {
        return value === false || value === undefined ? "—" : NUMBER.format(Math.round(value) || 0);
    }

    monthName(iso, withYear = true) {
        const [year, month] = iso.split("-").map(Number);
        return withYear ? `${MONTHS[month - 1]} ${year}` : MONTHS[month - 1];
    }

    // ---------------------------------------------------------------- actions
    confirmDiscard() {
        if (!this.state.board || !this.dirty.length) {
            return Promise.resolve(true);
        }
        return new Promise((resolve) => {
            this.dialog.add(
                ConfirmationDialog,
                {
                    body: `มีเป้าที่แก้ ${this.dirty.length} รายการยังไม่บันทึก ต้องการทิ้งการแก้ไขหรือไม่`,
                    confirmLabel: "ทิ้งการแก้ไข",
                    confirm: () => resolve(true),
                    cancelLabel: "กลับไปแก้ต่อ",
                    cancel: () => resolve(false),
                },
                { onClose: () => resolve(false) }
            );
        });
    }

    async move(step) {
        if (!(await this.confirmDiscard())) {
            return;
        }
        const [year, month] = this.state.month.split("-").map(Number);
        this.state.month = this.isoMonth(year, month - 1 + step);
        await this.load();
    }

    cancel() {
        this.state.edits = {};
    }

    async save() {
        const changes = this.dirty.map((row) => ({ level: row.level, id: row.id, amount: this.value(row) }));
        this.state.saving = true;
        try {
            const result = await this.orm.call(TARGET, "save_board", [this.state.month, changes]);
            await this.load();
            this.notification.add(`บันทึกเป้า ${result.saved} รายการ ลบ ${result.removed} รายการ`, { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    // ---------------------------------------------------------------- import
    onFile(ev) {
        this.readFile(ev.target.files[0]);
        // choosing the same file again must check it again
        ev.target.value = "";
    }

    onDrop(ev) {
        this.state.dragging = false;
        this.readFile(ev.dataTransfer.files[0]);
    }

    readFile(file) {
        if (!file) {
            return;
        }
        if (file.size > MAX_BYTES) {
            this.notification.add("ไฟล์ใหญ่เกิน 5 MB", { type: "warning" });
            return;
        }
        const reader = new FileReader();
        reader.onload = async () => {
            const data = reader.result.slice(reader.result.indexOf(",") + 1);
            this.state.file = { name: file.name, data, preview: null, busy: true };
            try {
                this.state.file.preview = await this.orm.call(IMPORT, "preview", [data]);
            } catch (error) {
                this.state.file = this.emptyFile();
                throw error;
            } finally {
                this.state.file.busy = false;
            }
        };
        reader.readAsDataURL(file);
    }

    clearFile() {
        this.state.file = this.emptyFile();
    }

    async applyFile() {
        // the import reloads the board: unsaved cells would be lost
        if (!(await this.confirmDiscard())) {
            return;
        }
        this.state.file.busy = true;
        try {
            const result = await this.orm.call(IMPORT, "apply", [this.state.file.data]);
            this.clearFile();
            await this.load();
            this.notification.add(
                `นำเข้าแล้ว: เพิ่ม ${result.created} แก้ ${result.updated} ข้าม ${result.skipped} แถว`,
                { type: "success" });
        } finally {
            this.state.file.busy = false;
        }
    }
}

registry.category("actions").add("buz_sales_dashboard.targets", SalesTargetBoard);
