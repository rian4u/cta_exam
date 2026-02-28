const message = document.getElementById("contact-message");
const emailLink = document.getElementById("contact-email-link");

function getApiBaseCandidates() {
  const candidates = [];
  const { origin, protocol, hostname } = window.location;
  if (origin && origin !== "null" && protocol.startsWith("http")) {
    candidates.push(origin);
  }
  if (hostname) {
    candidates.push(`http://${hostname}:8000`);
  }
  candidates.push("http://127.0.0.1:8000");
  candidates.push("http://localhost:8000");
  return [...new Set(candidates)];
}

async function fetchContactInfo() {
  for (const base of getApiBaseCandidates()) {
    try {
      const response = await fetch(`${base}/api/contact`, { mode: "cors" });
      if (!response.ok) {
        continue;
      }
      const payload = await response.json();
      const email = String(payload.email || "").trim();
      if (email && emailLink) {
        emailLink.href = `mailto:${email}`;
        emailLink.textContent = email;
      }
      if (message && payload.message) {
        message.textContent = String(payload.message);
      }
      return;
    } catch (_) {}
  }
}

fetchContactInfo();
