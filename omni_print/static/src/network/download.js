/** @odoo-module **/

import { download, downloadFile } from "@web/core/network/download"
import { makeErrorFromResponse, ConnectionLostError } from "@web/core/network/rpc_service"

const _download = download._download

export function sendToPrinter({ file, reportName, reportTitle, docNames }, proxyUrl = "http://127.0.0.1:32276/print/pdf") {
    const formData = new FormData();
    formData.append("file", file, reportName);
    formData.append("reportName", reportName);
    formData.append("reportTitle", reportTitle);
    formData.append("docNames", docNames);

    return fetch(proxyUrl, {
        method: "POST",
        body: formData,
        headers: {
            "Access-Control-Allow-Origin": "*",
            "Accept-Referrer-Policy": "no-referrer",
        },
    });
}


download._download = async function (options) {
    if (!options.url || options.url !== "/report/download") {
        return _download.apply(this, arguments)
    }

    const [_, reportType] = JSON.parse(options.data.data)
    if (reportType !== "qweb-pdf" && reportType !== "qweb-text") {
        return _download.apply(this, arguments)
    }

    const formData = new FormData(options.form || undefined)
    if (!options.form) {
        Object.entries(options.data).forEach(([key, value]) => formData.append(key, value))
    }
    formData.append("token", "dummy-because-api-expects-one")
    if (window.odoo && window.odoo.csrf_token) {
        formData.append("csrf_token", window.odoo.csrf_token)
    }

    return fetch(options.form ? options.form.action : options.url, {
        method: options.form ? options.form.method : "POST",
        body: formData,
    }).then((response) => {
        handleResponse(response, reportType)
    }).catch((error) => {
        Promise.reject(new ConnectionLostError())
    })
}

function handleResponse(response, reportType) {
    if (!response.ok) {
        return response.text().then((text) => parseError(text, response.status))
    }

    const filename = parseContentDisposition(response.headers.get("Content-Disposition"))
    return response
        .blob()
        .then(async (blob) => {
            const mimetype = blob.type
            if (mimetype === "text/html" || !filename) {
                return Promise.reject(new Error("Invalid MIME type or filename missing."))
            }

            function getDecodedHeader(key) {
                return response.headers.get(key) && decodeURIComponent(response.headers.get(key))
            }

            const printData = {
                file: blob,
                filename,
                reportName: getDecodedHeader("X-Report-Name") || "",
                reportTitle: getDecodedHeader("X-Report-Title") || "",
                docNames: getDecodedHeader("X-Report-Docnames") || removeExtension(filename) || ""
            };
            
            const format = reportType === "qweb-pdf" ? "pdf" : "zpl"
            const proxyUrl = `http://127.0.0.1:32276/print/${format}`
            return sendToPrinter(printData, proxyUrl)
                .then(async (uploadResponse) => {
                    if (uploadResponse && !uploadResponse.ok) {
                        return uploadResponse.text().then((text) => Promise.reject(new Error(text)));
                    }
                    return Promise.resolve()
                }).then(() => Promise.resolve(filename))
                .catch((error) => {
                    console.log('print error = ', error);
                    downloadFile(blob, filename, mimetype);
                    return Promise.resolve(filename);
                });
        });
}

function parseError(text, status) {
    const doc = new DOMParser().parseFromString(text, "text/html")
    const nodes = doc.body.children.length ? doc.body.children : [doc.body]
    let error = {
        message: "Arbitrary Uncaught Python Exception",
        data: {
            debug: `${status}\n${nodes[0].textContent}\n${nodes.length > 1 ? nodes[1].textContent : ""}`,
        },
    }
    return Promise.reject(makeErrorFromResponse(error))
}

function parseContentDisposition(contentDisposition) {
    if (!contentDisposition) {
        return null
    }

    const filenameRfc5987Regex = /filename\*=([^';]+)'([^';]*)'([^';]*)/
    const matchesRfc5987 = filenameRfc5987Regex.exec(contentDisposition)
    if (matchesRfc5987 && matchesRfc5987.length === 4) {
        const charset = matchesRfc5987[1]
        const language = matchesRfc5987[2]
        const encodedFilename = matchesRfc5987[3]
        const decodedFilename = decodeURIComponent(encodedFilename)
        return decodedFilename
    }

    const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/
    const matches = filenameRegex.exec(contentDisposition)
    if (matches != null && matches[1]) {
        const filename = matches[1].replace(/['"]/g, "")
        return decodeURIComponent(filename)
    }

    return null
}

export function removeExtension(filename) {
    return filename.replace(/\.[^/.]+$/, "");
}
