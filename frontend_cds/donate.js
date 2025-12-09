// Configurable backend URL. Replace with your deployed backend (HTTPS) when ready.
const BACKEND_URL = (function(){
    // If you host backend on a different domain, set it here, e.g.:
    // return 'https://api.yourdomain.com';
    return 'http://127.0.0.1:5000';
})();

const form = document.getElementById("donationForm");
if (form) {
    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const data = {
            fullname: document.getElementById("fullname").value,
            statecode: document.getElementById("statecode").value,
            phone: document.getElementById("phone").value,
            amount: document.getElementById("amount").value
        };

        const statusEl = document.getElementById("status");
        if (statusEl) statusEl.innerText = "Processing...";

        try {
            const resp = await fetch(`${BACKEND_URL}/donate`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(data)
            });

            if (!resp.ok) {
                const text = await resp.text();
                if (statusEl) statusEl.innerText = `Error from server: ${resp.status} ${text}`;
                return;
            }

            const result = await resp.json();
            if (result.payment_url) {
                if (statusEl) statusEl.innerText = "Redirecting to payment provider...";
                window.location.href = result.payment_url;
            } else {
                if (statusEl) statusEl.innerText = "Error: " + (result.message || 'Unknown error');
            }
        } catch (err) {
            if (statusEl) statusEl.innerText = "Network error: " + err.message;
        }
    });
} else {
    console.warn('donationForm not found on page');
}
