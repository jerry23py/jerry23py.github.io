// Backend URL comes from `frontend_cds/config.js` (window.BACKEND_URL).
// Fall back to localhost for local development if not provided.
const BACKEND_URL = window.BACKEND_URL || 'http://127.0.0.1:5000';

const form = document.getElementById("donationForm");
if (form) {
    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const statusEl = document.getElementById("status");
        const loadingModal = document.getElementById('loadingModal');
        const loadingText = document.getElementById('loadingText');
        function showLoading(text){ if (loadingText) loadingText.innerText = text; if (loadingModal) loadingModal.style.display = 'flex'; }
        function hideLoading(){ if (loadingModal) loadingModal.style.display = 'none'; }

        if (statusEl) statusEl.innerText = "Processing...";
        showLoading('Uploading proof…');

        const fd = new FormData();
        fd.append('fullname', document.getElementById("fullname").value);
        fd.append('email', document.getElementById("email").value);
        fd.append('phone', document.getElementById("phone").value);
        fd.append('amount', document.getElementById("amount").value);
        const proofFile = document.getElementById('proof').files[0];
        if (!proofFile) {
            if (statusEl) statusEl.innerText = 'Please attach a proof of payment file.';
            hideLoading();
            return;
        }
        fd.append('proof', proofFile);

        try {
            const resp = await fetch(`${BACKEND_URL}/donate`, {
                method: "POST",
                body: fd
            });

            if (!resp.ok) {
                const text = await resp.text();
                if (statusEl) statusEl.innerText = `Error from server: ${resp.status} ${text}`;
                return;
            }

            const result = await resp.json();
            if (result.reference) {
                if (statusEl) statusEl.innerText = `Donation recorded. Reference: ${result.reference}. ${result.message || ''}`;
                showLoading('Done');
                // show 'Done' briefly then hide
                setTimeout(() => { hideLoading(); }, 1500);
                // Optionally show instructions or copy reference to clipboard
                try { navigator.clipboard?.writeText(result.reference); } catch (e) {}
            } else {
                if (statusEl) statusEl.innerText = "Error: " + (result.message || 'Unknown error');
                showLoading('Error');
                setTimeout(() => { hideLoading(); }, 1500);
            }

        } catch (err) {
            if (statusEl) statusEl.innerText = "Network error: " + err.message;
            hideLoading();
        }
    });
}
        } catch (err) {
            if (statusEl) statusEl.innerText = "Network error: " + err.message;
        }
    });
} else {
    console.warn('donationForm not found on page');
}

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
