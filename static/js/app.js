const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const resultZone = document.getElementById("result-zone");
const errorZone = document.getElementById("error-zone");
const resultTemplate = document.getElementById("result-template");
const chips = document.querySelectorAll(".chip");

const analyzeForm = document.getElementById("analyze-form");
const analyzeInput = document.getElementById("analyze-input");
const analyzeOutput = document.getElementById("analyze-output");
const analyzeHtml = document.getElementById("analyze-html");
const analyzeLegend = document.getElementById("analyze-legend");

function showError(message) {
  errorZone.hidden = false;
  errorZone.textContent = message;
  resultZone.hidden = true;
}

function clearError() {
  errorZone.hidden = true;
  errorZone.textContent = "";
}

function fieldBlock(label, value) {
  if (!value) return "";
  return `
    <div>
      <p class="field-label">${label}</p>
      <p class="field-value">${escapeHtml(value)}</p>
    </div>
  `;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderResult(payload) {
  const { result, dictionary_match: match } = payload;
  const node = resultTemplate.content.cloneNode(true);
  const card = node.querySelector(".specimen-card");

  const type = result.type || "unknown";
  const tab = node.querySelector("[data-tab]");
  const name = node.querySelector("[data-name]");
  const badge = node.querySelector("[data-badge]");
  const body = node.querySelector("[data-body]");
  const meta = node.querySelector("[data-meta]");

  tab.textContent = type === "drug" ? "chemical entity" : type === "disease" ? "condition" : "unclassified";
  name.textContent = result.name || payload.query;

  badge.classList.add(type);
  badge.textContent = type === "drug" ? "Drug / Chemical" : type === "disease" ? "Disease" : "Unknown";

  let bodyHtml = "";
  if (type === "drug") {
    bodyHtml += fieldBlock("Used for", result.used_for);
    bodyHtml += fieldBlock("How it works", result.how_it_works);
    bodyHtml += fieldBlock("Common side effects", result.common_side_effects);
  } else if (type === "disease") {
    bodyHtml += fieldBlock("Overview", result.overview);
    bodyHtml += fieldBlock("Symptoms", result.symptoms);
    bodyHtml += fieldBlock("Prevention & management", result.prevention);
    bodyHtml += fieldBlock("When to see a doctor", result.when_to_see_doctor);
  } else {
    bodyHtml += fieldBlock("Note", result.note || "Could not confidently classify this term.");
  }
  body.innerHTML = bodyHtml;

  if (result.disclaimer) {
    body.innerHTML += `<p class="disclaimer">${escapeHtml(result.disclaimer)}</p>`;
  }

  const metaParts = [];
  if (match) {
    metaParts.push(`reference index: ${match.confidence} match &middot; ${match.label.toLowerCase()}`);
    if (match.mesh_id) metaParts.push(`MeSH ${match.mesh_id}`);
  } else {
    metaParts.push("reference index: no match &mdash; classified by AI only");
  }
  meta.innerHTML = metaParts.map((p) => `<span>${p}</span>`).join("");

  resultZone.innerHTML = "";
  resultZone.appendChild(node);
  resultZone.hidden = false;
}

async function runSearch(term) {
  clearError();
  const button = searchForm.querySelector("button");
  button.disabled = true;
  button.textContent = "Identifying\u2026";

  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ term }),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Something went wrong. Please try again.");
      return;
    }
    renderResult(data);
  } catch (err) {
    showError("Network error \u2014 please check your connection and try again.");
  } finally {
    button.disabled = false;
    button.textContent = "Identify";
  }
}

searchForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const term = searchInput.value.trim();
  if (term) runSearch(term);
});

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const term = chip.dataset.term;
    searchInput.value = term;
    runSearch(term);
  });
});

analyzeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = analyzeInput.value.trim();
  if (!text) return;

  const button = analyzeForm.querySelector("button");
  button.disabled = true;
  button.textContent = "Scanning\u2026";

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Could not scan that text.");
      return;
    }

    analyzeHtml.innerHTML = data.html_text || "(no matches found)";
    analyzeLegend.innerHTML = `
      <span><i class="chemical"></i>Chemical</span>
      <span><i class="disease"></i>Disease</span>
    `;
    analyzeOutput.hidden = false;
  } catch (err) {
    showError("Network error \u2014 please check your connection and try again.");
  } finally {
    button.disabled = false;
    button.textContent = "Scan text";
  }
});
