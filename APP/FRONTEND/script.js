/* =========================================================
   ZIPPZO WMS — COMPLETE MASTER JAVASCRIPT
   Brand / Shared Frontend Controller
   ========================================================= */

"use strict";

/* =========================================================
   GLOBAL CONFIGURATION
   ========================================================= */

const API_BASE = window.location.origin;

const TOKEN_KEY = "zippzo_session_token";
const USER_KEY = "zippzo_user";

/* =========================================================
   AUTH / SESSION
   ========================================================= */

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function getSavedUser() {
    try {
        return JSON.parse(
            localStorage.getItem(USER_KEY) || "null"
        );
    } catch (error) {
        return null;
    }
}

function saveUser(user) {
    if (!user) {
        localStorage.removeItem(USER_KEY);
        return;
    }

    localStorage.setItem(
        USER_KEY,
        JSON.stringify(user)
    );
}

function authHeaders(json = false) {
    const headers = {};

    const token = getToken();

    if (json) {
        headers["Content-Type"] =
            "application/json";
    }

    if (token) {
        headers["Authorization"] =
            `Bearer ${token}`;
    }

    return headers;
}

/* =========================================================
   API REQUEST
   ========================================================= */

async function apiFetch(
    path,
    options = {}
) {
    const method =
        String(
            options.method || "GET"
        ).toUpperCase();

    const headers = {
        ...authHeaders(
            Boolean(options.body) ||
            ["POST", "PUT", "PATCH"].includes(
                method
            )
        ),
        ...(options.headers || {})
    };

    const response = await fetch(
        `${API_BASE}${path}`,
        {
            ...options,
            method,
            headers
        }
    );

    if (response.status === 401) {
        sessionExpired();
    }

    return response;
}

/* =========================================================
   JSON REQUEST
   ========================================================= */

async function api(
    path,
    options = {}
) {
    const response =
        await apiFetch(
            path,
            options
        );

    const text =
        await response.text();

    let data = {};

    try {
        data =
            text
                ? JSON.parse(text)
                : {};
    } catch (error) {
        data = {
            raw: text
        };
    }

    if (!response.ok) {
        const message =
            data?.detail ||
            data?.message ||
            data?.error ||
            `HTTP ${response.status}`;

        const error =
            new Error(message);

        error.status =
            response.status;

        error.data = data;

        throw error;
    }

    return data;
}

/* =========================================================
   API FALLBACK
   ========================================================= */

async function apiFallback(
    paths,
    options = {}
) {
    let lastError = null;

    for (const path of paths) {

        try {

            return await api(
                path,
                options
            );

        } catch (error) {

            lastError = error;

            if (
                error.status === 401 ||
                error.status === 403
            ) {
                throw error;
            }
        }
    }

    throw (
        lastError ||
        new Error(
            "API endpoint not available"
        )
    );
}

/* =========================================================
   ARRAY NORMALIZER
   ========================================================= */

function normalizeArray(data) {

    if (Array.isArray(data)) {
        return data;
    }

    if (
        Array.isArray(
            data?.items
        )
    ) {
        return data.items;
    }

    if (
        Array.isArray(
            data?.data
        )
    ) {
        return data.data;
    }

    if (
        Array.isArray(
            data?.results
        )
    ) {
        return data.results;
    }

    if (
        Array.isArray(
            data?.records
        )
    ) {
        return data.records;
    }

    return [];
}

/* =========================================================
   SESSION EXPIRED
   ========================================================= */

function sessionExpired() {

    localStorage.removeItem(
        TOKEN_KEY
    );

    localStorage.removeItem(
        USER_KEY
    );

    if (
        !window.location.pathname.endsWith(
            "index.html"
        )
    ) {
        window.location.href =
            "index.html";
    }
}

/* =========================================================
   CURRENT USER
   ========================================================= */

async function getCurrentUser() {

    const token =
        getToken();

    if (!token) {
        return null;
    }

    try {

        const user =
            await api(
                "/api/auth/me"
            );

        saveUser(user);

        updateUserUI(user);

        return user;

    } catch (error) {

        if (
            error.status === 401
        ) {
            return null;
        }

        console.error(
            "User loading error:",
            error
        );

        return null;
    }
}

/* =========================================================
   USER UI
   ========================================================= */

function updateUserUI(
    user
) {

    if (!user) {
        return;
    }

    const name =
        user?.employee?.name ||
        user?.name ||
        user?.full_name ||
        user?.user?.name ||
        "Zippzo User";

    const role =
        user?.employee?.role_name ||
        user?.role ||
        user?.role_name ||
        user?.user?.role ||
        "EMPLOYEE";

    document
        .querySelectorAll(
            "#userName," +
            ".user-name," +
            "[data-user-name]"
        )
        .forEach(
            element => {
                element.textContent =
                    name;
            }
        );

    document
        .querySelectorAll(
            "#userRole," +
            ".user-role," +
            "[data-user-role]"
        )
        .forEach(
            element => {
                element.textContent =
                    role;
            }
        );
}

/* =========================================================
   LOGIN CHECK
   ========================================================= */

async function checkSession() {

    if (!getToken()) {
        return null;
    }

    return await getCurrentUser();
}

/* =========================================================
   LOGOUT
   ========================================================= */

async function logout() {

    const token =
        getToken();

    try {

        if (token) {

            await fetch(
                `${API_BASE}/api/auth/logout`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json",

                        "Authorization":
                            `Bearer ${token}`
                    },

                    body:
                        JSON.stringify({
                            session_token:
                                token
                        })
                }
            );
        }

    } catch (error) {

        console.warn(
            "Logout error:",
            error
        );

    } finally {

        localStorage.removeItem(
            TOKEN_KEY
        );

        localStorage.removeItem(
            USER_KEY
        );

        window.location.href =
            "index.html";
    }
}

/* =========================================================
   DASHBOARD
   ========================================================= */

async function loadDashboard() {

    if (!getToken()) {
        return null;
    }

    try {

        const data =
            await api(
                "/api/dashboard"
            );

        setText(
            "totalProducts",
            data.total_products
        );

        setText(
            "totalLocations",
            data.total_locations
        );

        setText(
            "totalSuppliers",
            data.total_suppliers
        );

        setText(
            "totalInventory",
            data.total_inventory_records
        );

        setText(
            "totalStock",
            data.total_stock
        );

        setText(
            "totalOrders",
            data.total_orders
        );

        return data;

    } catch (error) {

        console.warn(
            "Dashboard error:",
            error.message
        );

        return null;
    }
}

/* =========================================================
   HEALTH
   ========================================================= */

async function checkSystemHealth() {

    try {

        return await api(
            "/api/health"
        );

    } catch (error) {

        console.warn(
            "Health check failed:",
            error.message
        );

        return null;
    }
}

/* =========================================================
   TEXT HELPER
   ========================================================= */

function setText(
    id,
    value
) {

    const element =
        document.getElementById(id);

    if (!element) {
        return;
    }

    element.textContent =
        value === undefined ||
        value === null ||
        value === ""
            ? "0"
            : value;
}

/* =========================================================
   SAFE VALUE
   ========================================================= */

function safe(
    value,
    fallback = ""
) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return fallback;
    }

    return value;
}

/* =========================================================
   HTML ESCAPE
   ========================================================= */

function escapeHtml(
    value
) {

    return String(
        value ?? ""
    )
        .replaceAll(
            "&",
            "&amp;"
        )
        .replaceAll(
            "<",
            "&lt;"
        )
        .replaceAll(
            ">",
            "&gt;"
        )
        .replaceAll(
            '"',
            "&quot;"
        )
        .replaceAll(
            "'",
            "&#039;"
        );
}

/* =========================================================
   NUMBER
   ========================================================= */

function numberValue(
    value
) {

    const number =
        Number(value);

    return Number.isFinite(
        number
    )
        ? number
        : 0;
}

/* =========================================================
   NUMBER FORMAT
   ========================================================= */

function formatNumber(
    value,
    decimals = 0
) {

    return numberValue(
        value
    ).toLocaleString(
        "en-IN",
        {
            minimumFractionDigits:
                decimals,

            maximumFractionDigits:
                decimals
        }
    );
}

/* =========================================================
   CURRENCY
   ========================================================= */

function formatCurrency(
    value
) {

    return `₹${formatNumber(
        value,
        2
    )}`;
}

/* =========================================================
   DATE
   ========================================================= */

function formatDate(
    value
) {

    if (!value) {
        return "—";
    }

    const date =
        new Date(value);

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return String(value);
    }

    return date.toLocaleDateString(
        "en-IN"
    );
}

/* =========================================================
   DATE + TIME
   ========================================================= */

function formatDateTime(
    value
) {

    if (!value) {
        return "—";
    }

    const date =
        new Date(value);

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return String(value);
    }

    return date.toLocaleString(
        "en-IN"
    );
}

/* =========================================================
   NAVIGATION
   ========================================================= */

function openPage(
    page
) {

    if (!page) {
        return;
    }

    window.location.href =
        page;
}

function go(
    page
) {
    openPage(page);
}

function showDashboard() {
    openPage(
        "index.html"
    );
}

/* =========================================================
   MASTER DATA
   ========================================================= */

function openProducts() {
    openPage(
        "products.html"
    );
}

function openSuppliers() {
    openPage(
        "suppliers.html"
    );
}

function openLocations() {
    openPage(
        "locations.html"
    );
}

/* =========================================================
   HR
   ========================================================= */

function openHRDashboard() {
    openPage(
        "hr-dashboard.html"
    );
}

function openHRLive() {
    openPage(
        "hr-live.html"
    );
}

function openEmployees() {
    openPage(
        "employees.html"
    );
}

function openAttendance() {
    openPage(
        "attendance.html"
    );
}

function openShiftManagement() {
    openPage(
        "shift-management.html"
    );
}

function openLeaveManagement() {
    openPage(
        "leave-management.html"
    );
}

function openPayroll() {
    openPage(
        "payroll.html"
    );
}

function openEmployeeDocuments() {
    openPage(
        "employee-documents.html"
    );
}

function openEmployeePerformance() {
    openPage(
        "employee-performance.html"
    );
}

function openHRReports() {
    openPage(
        "hr-reports.html"
    );
}

/* =========================================================
   WAREHOUSE
   ========================================================= */

function openInventory() {
    openPage(
        "inventory.html"
    );
}

function openBins() {
    openPage(
        "bins.html"
    );
}

function openStockMovements() {
    openPage(
        "stock-movements.html"
    );
}

/* =========================================================
   INBOUND
   ========================================================= */

function openPurchaseOrders() {
    openPage(
        "purchase-orders.html"
    );
}

function openGRN() {
    openPage(
        "grn.html"
    );
}

function openPutaway() {
    openPage(
        "putaway.html"
    );
}

function openGridPutaway() {
    openPage(
        "grid-putaway.html"
    );
}

/* =========================================================
   ORDERS
   ========================================================= */

function openOrders() {
    openPage(
        "orders.html"
    );
}

function openCreateBatch() {
    openPage(
        "create-batch.html"
    );
}

function openPicking() {
    openPage(
        "picking.html"
    );
}

function openSorting() {
    openPage(
        "sorting.html"
    );
}

/*
   IMPORTANT:
   Dropping is NOT a separate Zippzo module.

   Old pages which still call openDropping()
   are redirected to Sorting.
*/

function openDropping() {
    openPage(
        "sorting.html"
    );
}

/* =========================================================
   DELIVERY / DISPATCH
   ========================================================= */

function openRiders() {
    openPage(
        "riders.html"
    );
}

function openVehicleArrival() {
    openPage(
        "vehicle-arrival.html"
    );
}

function openDispatch() {
    openPage(
        "dispatch.html"
    );
}

function openStoreReceiving() {
    openPage(
        "store-receiving.html"
    );
}

/* =========================================================
   REPORTS
   ========================================================= */

function openStockReport() {
    openPage(
        "stock-report.html"
    );
}

function openGRNReport() {
    openPage(
        "grn-report.html"
    );
}

function openPutawayReport() {
    openPage(
        "putaway-report.html"
    );
}

function openOrderReport() {
    openPage(
        "order-report.html"
    );
}

function openPickingReport() {
    openPage(
        "picking-report.html"
    );
}

function openSortingReport() {
    openPage(
        "sorting-report.html"
    );
}

function openPickingIPP() {
    openPage(
        "picking-ipp.html"
    );
}

function openSortingIPP() {
    openPage(
        "sorting-ipp.html"
    );
}

function openGridPutawayReport() {
    openPage(
        "grid-putaway-report.html"
    );
}

function openVehicleArrivalReport() {
    openPage(
        "vehicle-arrival-report.html"
    );
}

function openDispatchReport() {
    openPage(
        "dispatch-report.html"
    );
}

function openStoreReceivingReport() {
    openPage(
        "store-receiving-report.html"
    );
}

/* =========================================================
   ADMIN
   ========================================================= */

function openAccessControl() {
    openPage(
        "access-control.html"
    );
}

function openAuditLogs() {
    openPage(
        "audit-logs.html"
    );
}

function openSystemSettings() {
    openPage(
        "system-settings.html"
    );
}

/* =========================================================
   TOAST
   ========================================================= */

function showToast(
    message,
    type = "info"
) {

    let toast =
        document.getElementById(
            "zippzoToast"
        );

    if (!toast) {

        toast =
            document.createElement(
                "div"
            );

        toast.id =
            "zippzoToast";

        toast.className =
            "toast";

        document.body.appendChild(
            toast
        );
    }

    toast.className =
        `toast show ${type}`;

    toast.textContent =
        message;

    clearTimeout(
        window.zippzoToastTimer
    );

    window.zippzoToastTimer =
        setTimeout(
            () => {
                toast.classList.remove(
                    "show"
                );
            },
            3200
        );
}

function showMessage(
    message,
    isError = false
) {

    showToast(
        message,
        isError
            ? "error"
            : "success"
    );
}

/* =========================================================
   LOADING
   ========================================================= */

function setLoading(
    element,
    loading = true
) {

    if (!element) {
        return;
    }

    element.classList.toggle(
        "loading",
        loading
    );

    element.disabled =
        loading;
}

function showLoading(
    message = "Loading..."
) {

    let overlay =
        document.getElementById(
            "zippzoLoadingOverlay"
        );

    if (!overlay) {

        overlay =
            document.createElement(
                "div"
            );

        overlay.id =
            "zippzoLoadingOverlay";

        overlay.className =
            "loading-overlay";

        overlay.innerHTML = `
            <div class="spinner"></div>
            <div class="loading-text"></div>
        `;

        document.body.appendChild(
            overlay
        );
    }

    const text =
        overlay.querySelector(
            ".loading-text"
        );

    if (text) {
        text.textContent =
            message;
    }

    overlay.classList.add(
        "show"
    );
}

function hideLoading() {

    const overlay =
        document.getElementById(
            "zippzoLoadingOverlay"
        );

    if (overlay) {
        overlay.classList.remove(
            "show"
        );
    }
}

/* =========================================================
   MODAL
   ========================================================= */

function openModal(
    id
) {

    const modal =
        document.getElementById(
            id
        );

    if (!modal) {
        return;
    }

    modal.classList.add(
        "show"
    );

    modal.classList.add(
        "open"
    );
}

function closeModal(
    id
) {

    const modal =
        document.getElementById(
            id
        );

    if (!modal) {
        return;
    }

    modal.classList.remove(
        "show"
    );

    modal.classList.remove(
        "open"
    );
}

/* =========================================================
   CSV
   ========================================================= */

function csvCell(
    value
) {

    return `"${String(
        value ?? ""
    ).replaceAll(
        '"',
        '""'
    )}"`;
}

function downloadCSV(
    filename,
    headers,
    rows
) {

    const csv =
        [
            headers,
            ...rows
        ]
            .map(
                row =>
                    row
                        .map(
                            csvCell
                        )
                        .join(",")
            )
            .join("\n");

    const blob =
        new Blob(
            [csv],
            {
                type:
                    "text/csv;charset=utf-8;"
            }
        );

    const url =
        URL.createObjectURL(
            blob
        );

    const link =
        document.createElement(
            "a"
        );

    link.href =
        url;

    link.download =
        filename;

    document.body.appendChild(
        link
    );

    link.click();

    link.remove();

    URL.revokeObjectURL(
        url
    );
}

/* =========================================================
   PRINT
   ========================================================= */

function printReport() {
    window.print();
}

/* =========================================================
   INPUT HELPERS
   ========================================================= */

function getValue(
    id
) {

    const element =
        document.getElementById(
            id
        );

    return element
        ? element.value
        : "";
}

function setValue(
    id,
    value
) {

    const element =
        document.getElementById(
            id
        );

    if (element) {
        element.value =
            value ?? "";
    }
}

function clearValue(
    id
) {

    const element =
        document.getElementById(
            id
        );

    if (element) {
        element.value =
            "";
    }
}

/* =========================================================
   ACTIVE NAVIGATION
   ========================================================= */

function setActiveNavigation() {

    const current =
        window.location.pathname
            .split("/")
            .pop()
            .toLowerCase();

    document
        .querySelectorAll(
            "[data-page]," +
            "[data-nav-page]"
        )
        .forEach(
            element => {

                const page =
                    element.dataset.page ||
                    element.dataset.navPage ||
                    "";

                element.classList.toggle(
                    "active",
                    page.toLowerCase() ===
                    current
                );
            }
        );
}

/* =========================================================
   KEYBOARD
   ========================================================= */

document.addEventListener(
    "keydown",
    event => {

        if (
            event.key !==
            "Escape"
        ) {
            return;
        }

        document
            .querySelectorAll(
                ".modal.show," +
                ".modal.open"
            )
            .forEach(
                modal => {

                    modal.classList.remove(
                        "show"
                    );

                    modal.classList.remove(
                        "open"
                    );
                }
            );
    }
);

/* =========================================================
   MODAL CLOSE BUTTONS
   ========================================================= */

document.addEventListener(
    "click",
    event => {

        const target =
            event.target.closest(
                "[data-close-modal]"
            );

        if (!target) {
            return;
        }

        closeModal(
            target.dataset.closeModal
        );
    }
);

/* =========================================================
   PAGE INITIALIZATION
   ========================================================= */

async function initializeZippzoPage() {

    setActiveNavigation();

    if (!getToken()) {
        return null;
    }

    return await getCurrentUser();
}

/* =========================================================
   DASHBOARD AUTO REFRESH
   ========================================================= */

let dashboardTimer =
    null;

function startDashboardRefresh() {

    const dashboardExists =
        document.getElementById(
            "totalProducts"
        ) ||
        document.getElementById(
            "totalOrders"
        ) ||
        document.getElementById(
            "totalStock"
        );

    if (!dashboardExists) {
        return;
    }

    if (dashboardTimer) {
        clearInterval(
            dashboardTimer
        );
    }

    dashboardTimer =
        setInterval(
            loadDashboard,
            10000
        );
}

/* =========================================================
   PAGE START
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    async () => {

        try {

            await initializeZippzoPage();

            const dashboard =
                document.getElementById(
                    "totalProducts"
                ) ||
                document.getElementById(
                    "totalOrders"
                ) ||
                document.getElementById(
                    "totalStock"
                );

            if (dashboard) {

                await Promise.all([
                    loadDashboard(),
                    checkSystemHealth()
                ]);

                startDashboardRefresh();
            }

        } catch (error) {

            console.error(
                "Zippzo WMS startup error:",
                error
            );
        }
    }
);