// Backend URL comes from `frontend_cds/config.js` (window.BACKEND_URL).
// Fall back to localhost for local development if not provided.
const BACKEND_URL = window.BACKEND_URL || 'http://127.0.0.1:5000';

// ----------------- DONATION FORM SUBMISSION -----------------
const form = document.getElementById("donationForm");

if (!form) {
    console.warn("donationForm not found");
    return;
}

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    // HARD LOCK
    if (form.dataset.submitted === "true") return;
    form.dataset.submitted = "true";

    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.innerText = "Processing...";

    const statusEl = document.getElementById("status");
    const loadingModal = document.getElementById("loadingModal");
    const loadingText = document.getElementById("loadingText");

    const showLoading = (text) => {
        if (loadingText) loadingText.innerText = text;
        if (loadingModal) loadingModal.style.display = "flex";
    };

    const hideLoading = () => {
        if (loadingModal) loadingModal.style.display = "none";
    };

    showLoading("Uploading proof…");
    if (statusEl) statusEl.innerText = "Processing...";

    const proofFile = document.getElementById("proof").files[0];
    if (!proofFile) {
        alert("Please attach proof of payment.");
        reset();
        return;
    }

    const fd = new FormData(form);
    fd.append("proof", proofFile);

    try {
        const resp = await fetch(`${BACKEND_URL}/donate`, {
            method: "POST",
            body: fd
        });

        if (!resp.ok) {
            throw new Error(await resp.text());
        }

        const result = await resp.json();

        if (result.reference) {
            if (statusEl) {
                statusEl.innerText = `Donation recorded. Reference: ${result.reference}`;
            }
            showLoading("Done");
            setTimeout(hideLoading, 1500);
        } else {
            throw new Error(result.message || "Unknown error");
        }

    } catch (err) {
        console.error(err);
        alert("Payment failed.");
        reset();
    }

    function reset() {
        delete form.dataset.submitted;
        submitButton.disabled = false;
        submitButton.innerText = "Pay Now";
        hideLoading();
    }
});


// ----------------- LOAD BANK ACCOUNTS FOR DONATION FORM -----------------
(async function loadAvailableBanks(){
    const container = document.getElementById('bankAccounts');
    if (!container) return;
    try {
        const resp = await fetch(`${BACKEND_URL}/bank-accounts`);
        if (!resp.ok) { container.innerText = 'Unable to fetch bank transfer details.'; return; }
        const accounts = await resp.json();
        if (!accounts || accounts.length === 0) { container.innerText = 'No bank transfer details available at the moment.'; return; }
        container.innerHTML = '<strong>Bank Transfer Details</strong><div style="margin-top:6px;">' + accounts.map(a => `\n            <label style="display:block;padding:8px;border:1px solid #eee;border-radius:8px;margin-top:6px;">\n                <input type="radio" name="bank_account_id" value="${a.id}" style="margin-right:8px"> <strong>${a.bank_name}</strong> — ${a.account_name} — ${a.account_number || ''} ${a.bank_type? '('+a.bank_type+')':''}\n            </label>`).join('\n') + '</div>';
    } catch (err) {
        container.innerText = 'Error loading bank accounts: ' + err.message;
    }
})();

// ------------------ CHECK STATUS ------------------
async function checkStatus() {
    const ref = document.getElementById('checkRef').value.trim();
    const statusResult = document.getElementById('statusResult');
    if (!ref) { statusResult.innerText = 'Enter a reference to check status'; return; }
    try {
        statusResult.innerText = 'Checking...';
        const resp = await fetch(`${BACKEND_URL}/donation-status/${encodeURIComponent(ref)}`);
        if (!resp.ok) { statusResult.innerText = 'Not found or server error'; return; }
        const data = await resp.json();
        let text = `Status: ${data.status}`;
        if (data.status === 'paid') {
            text += `\nApproved by: ${data.approved_by || 'admin'}`;
            if (data.approved_at) text += ` at ${data.approved_at}`;
        }
        statusResult.innerText = text;
    } catch (err) {
        statusResult.innerText = 'Network error: ' + err.message;
    }
}
