/** @odoo-module **/

/**
 * ตัวช่วยที่หน้าจอในโมดูลนี้ใช้ร่วมกัน
 *
 * แถบตัวกรองของรายงานกับของการ์ดสินค้าต้องให้ช่วงวันเดียวกันเป๊ะเมื่อกดปุ่มชื่อเดียวกัน
 * และหัวตารางสองชั้นต้องรวมคอลัมน์ด้วยกติกาเดียวกัน จึงเก็บไว้ที่เดียว
 */

export const DATE_PRESETS = [
    { id: "this_month", label: "เดือนนี้" },
    { id: "last_month", label: "เดือนก่อน" },
    { id: "this_quarter", label: "ไตรมาสนี้" },
    { id: "this_year", label: "ปีนี้" },
];

/** คืน {date_from, date_to} ของช่วงสำเร็จรูป */
export function presetRange(presetId) {
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
        const quarter = Math.floor(today.getMonth() / 3);
        from = new Date(today.getFullYear(), quarter * 3, 1);
        to = new Date(today.getFullYear(), quarter * 3 + 3, 0);
    } else {
        from = new Date(today.getFullYear(), 0, 1);
        to = new Date(today.getFullYear(), 11, 31);
    }
    return { date_from: isoDate(from), date_to: isoDate(to) };
}

/** ห้ามใช้ toISOString() — มันเลื่อนวันตาม UTC แล้วช่วงวันที่จะคลาดไปหนึ่งวัน */
export function isoDate(date) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** รวมคอลัมน์ที่อยู่กลุ่มเดียวกันติดกันเป็น colspan ของหัวตารางแถวบน */
export function headerGroups(columns) {
    const groups = [];
    for (const col of columns) {
        const last = groups[groups.length - 1];
        if (col.group && last && last.isGroup && last.label === col.group) {
            last.span += 1;
        } else if (col.group) {
            groups.push({ label: col.group, span: 1, isGroup: true });
        } else {
            groups.push({ label: col.label, span: 1, isGroup: false });
        }
    }
    return groups;
}
