/** @odoo-module **/

/** จำนวน — ทศนิยมตามความละเอียดของหน่วยนับ ค่าว่างเป็นขีดกลาง ไม่ใช่ 0 */
export function fmtQty(value, digits = 2) {
    if (value === null || value === undefined || value === false || isNaN(value)) {
        return "–";
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
