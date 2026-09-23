/** @odoo-module **/

/** จำนวน — ทศนิยมตามความละเอียดของหน่วยนับ ค่าว่างเป็นขีดกลาง ไม่ใช่ 0 */
export function fmtQty(value, digits = 2) {
    if (value === null || value === undefined || value === false || isNaN(value)) {
        return "-";
    }
    if (!value) {
        return "-";
    }
    return Number(value).toLocaleString("th-TH", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    });
}

/** มูลค่า — ทศนิยมตามสกุลเงินของบริษัท */
export function fmtMoney(value, digits = 2) {
    return fmtQty(value, digits);
}

/** จำนวนวัน — จำนวนเต็ม; 0 มีความหมาย (จ่ายวันนี้) จึงไม่เป็นขีดกลาง */
export function fmtDays(value) {
    if (value === null || value === undefined || value === false || isNaN(value)) {
        return "-";
    }
    return Math.round(Number(value)).toLocaleString("th-TH");
}

/** เดือน (MOS) — ทศนิยมหนึ่งตำแหน่ง */
export function fmtMonths(value) {
    if (value === null || value === undefined || value === false || isNaN(value)) {
        return "-";
    }
    return Number(value).toLocaleString("th-TH", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
    });
}

export function fmtPct(value) {
    if (value === null || value === undefined || value === false || isNaN(value)) {
        return "";
    }
    return `${Number(value).toLocaleString("th-TH", {
        minimumFractionDigits: 1, maximumFractionDigits: 1,
    })}%`;
}
