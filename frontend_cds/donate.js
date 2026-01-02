// Backend URL comes from `frontend_cds/config.js` (window.BACKEND_URL).
// Fall back to localhost for local development if not provided.
const BACKEND_URL = window.BACKEND_URL || 'http://127.0.0.1:5000';

// ----------------- DONATION FORM SUBMISSION -----------------
const form = document.getElementById("donationForm");

if (form) {
    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        if (form.dataset.submitted === "true") {
            alert("This donation has already been submitted.");
            return;
        }
        form.dataset.submitted = "true";

        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.innerText = "Processing...";

        const statusEl = document.getElementById("status");
        const loadingModal = document.getElementById('loadingModal');
        const loadingText = document.getElementById('loadingText');

        const showLoading = (text) => { if (loadingText) loadingText.innerText = text; if (loadingModal) loadingModal.style.display = 'flex'; }
        const hideLoading = () => { if (loadingModal) loadingModal.style.display = 'none'; }

        try {
            // ------------------- VALIDATE PROOF -------------------
            const proofFile = document.getElementById('proof').files[0];
            if (!proofFile) {
                alert("Please attach a proof of payment file.");
                throw new Error("Proof file missing");
            }

            showLoading('Uploading proof…');

            // ------------------- SUBMIT DONATION -------------------
            const formData = new FormData(form);
            const donationResp = await fetch("/donate", { method: "POST", body: formData });

            if (!donationResp.ok) {
                const err = await donationResp.json();
                throw new Error(err.message || "Donation failed");
            }

            const donationResult = await donationResp.json();

            // ------------------- UPLOAD PROOF -------------------
            const fd = new FormData();
            fd.append('fullname', document.getElementById("fullname").value);
            fd.append('email', document.getElementById("email").value);
            fd.append('phone', document.getElementById("phone").value);
            fd.append('amount', document.getElementById("amount").value);
            const bankRadio = document.querySelector('input[name="bank_account_id"]:checked');
            if (bankRadio) fd.append('bank_account_id', bankRadio.value);
            fd.append('proof', proofFile);

            const proofResp = await fetch(`${BACKEND_URL}/donate`, { method: "POST", body: fd });

            if (!proofResp.ok) {
                const text = await proofResp.text();
                throw new Error(`Proof upload failed: ${text}`);
            }

            const proofResult = await proofResp.json();

            // ------------------- SUCCESS -------------------
            alert(`Donation successful! Reference: ${proofResult.reference || 'N/A'}`);
            if (statusEl) statusEl.innerText = `Donation recorded. Reference: ${proofResult.reference || ''}`;
            showLoading('Done');
            setTimeout(hideLoading, 1500);

            try { navigator.clipboard?.writeText(proofResult.reference); } catch (e) {}

        } catch (error) {
            console.error(error);
            alert(error.message || "Payment failed.");

            // 🔓 Unlock form on failure
            delete form.dataset.submitted;

        } finally {
            submitButton.disabled = false;
            submitButton.innerText = "Pay Now";
            hideLoading();
        }
    });
}


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
