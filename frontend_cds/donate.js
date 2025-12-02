document.getElementById("donationForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const data = {
        fullname: document.getElementById("fullname").value,
        statecode: document.getElementById("statecode").value,
        phone: document.getElementById("phone").value,
        amount: document.getElementById("amount").value
    };

    document.getElementById("status").innerText = "Processing...";

    const response = await fetch("http://127.0.0.1:5000/donate", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
    });

    const result = await response.json();

    if (result.payment_url) {
        document.getElementById("status").innerText = "Redirecting to Paystack...";
        window.location.href = result.payment_url;  // send user to Paystack
    } else {
        document.getElementById("status").innerText = "Error: " + result.message;
    }
});
