/**
 * Frontend Controller for Universal Multi-Vendor EOL AI Scraper.
 * Supports 100 enterprise vendors, 6 visible workflow steps, Generic vs AI comparison,
 * multi-vendor crawling, 1 record per stage, UTC dates, and metadata inspection.
 */

// Global State
let rawProducts = [];
let filteredProducts = [];
let activeCategory = "ALL";
let activeStage = "ALL";
let activeSector = "ALL";
let sortField = "stage_date_utc";
let sortAscending = true;
let enterpriseVendors = [];

// DOM Elements
const tableBody = document.getElementById("tableBody");
const searchInput = document.getElementById("searchInput");
const clearSearchBtn = document.getElementById("clearSearchBtn");
const emptyState = document.getElementById("emptyState");
const resultsCount = document.getElementById("resultsCount");
const triggerCrawlBtn = document.getElementById("triggerCrawlBtn");
const crawlerProgressContainer = document.getElementById("crawlerProgressContainer");
const crawlerProgressText = document.getElementById("crawlerProgressText");
const crawlerProgressFill = document.getElementById("crawlerProgressFill");
const toggleConfigBtn = document.getElementById("toggleConfigBtn");
const configGrid = document.getElementById("configGrid");
const targetUrlInput = document.getElementById("targetUrlInput");
const vendorPresetSelect = document.getElementById("vendorPresetSelect");
const siteCrawlCheckbox = document.getElementById("siteCrawlCheckbox");
const aiProviderSelect = document.getElementById("aiProviderSelect");
const apiKeyLabelText = document.getElementById("apiKeyLabelText");
const apiKeyPortalLink = document.getElementById("apiKeyPortalLink");
const geminiApiKeyInput = document.getElementById("geminiApiKeyInput");
const geminiModelSelect = document.getElementById("geminiModelSelect");
const toggleApiKeyVisibility = document.getElementById("toggleApiKeyVisibility");
const geminiModelLabel = document.getElementById("geminiModelLabel");
const detailModal = document.getElementById("detailModal");
const closeModalBtn = document.getElementById("closeModalBtn");
const openComparisonBtn = document.getElementById("openComparisonBtn");
const comparisonModal = document.getElementById("comparisonModal");
const closeComparisonBtn = document.getElementById("closeComparisonBtn");
const comparisonTableContainer = document.getElementById("comparisonTableContainer");

const PROVIDER_METADATA = {
  gemini: {
    label: "Google Gemini API Key",
    linkText: "AI Studio Keys ↗",
    linkUrl: "https://aistudio.google.com/app/apikey",
    placeholder: "Paste GEMINI_API_KEY (AIza...)",
    models: [
      { value: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash Lite (Fastest & Free)" },
      { value: "gemini-3.5-flash", label: "Gemini 3.5 Flash (Production Default)" },
      { value: "gemini-2.0-flash", label: "Gemini 2.0 Flash (Next-Gen Fast)" },
      { value: "gemini-1.5-pro", label: "Gemini 1.5 Pro (Deep Reasoning)" },
    ]
  },
  openai: {
    label: "OpenAI API Key",
    linkText: "OpenAI Keys ↗",
    linkUrl: "https://platform.openai.com/api-keys",
    placeholder: "Paste OPENAI_API_KEY (sk-...)",
    models: [
      { value: "gpt-4o-mini", label: "OpenAI GPT-4o Mini (Cost-Efficient Default)" },
      { value: "gpt-4o", label: "OpenAI GPT-4o (High Accuracy Multimodal)" },
      { value: "o1-mini", label: "OpenAI o1-mini (Reasoning Model)" },
      { value: "o3-mini", label: "OpenAI o3-mini (Advanced Reasoning)" },
    ]
  },
  anthropic: {
    label: "Anthropic Claude API Key",
    linkText: "Anthropic Console ↗",
    linkUrl: "https://console.anthropic.com/",
    placeholder: "Paste ANTHROPIC_API_KEY (sk-ant-...)",
    models: [
      { value: "claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku (Lightning Fast)" },
      { value: "claude-3-5-sonnet-20241022", label: "Claude 3.5 Sonnet (State of the Art)" },
    ]
  },
  azure: {
    label: "Azure OpenAI Key",
    linkText: "Azure Portal ↗",
    linkUrl: "https://portal.azure.com/",
    placeholder: "Paste AZURE_OPENAI_API_KEY...",
    models: [
      { value: "azure/gpt-4o-mini", label: "Azure OpenAI: gpt-4o-mini deployment" },
      { value: "azure/gpt-4o", label: "Azure OpenAI: gpt-4o deployment" },
    ]
  },
  bedrock: {
    label: "AWS Access Key ID",
    linkText: "AWS Console ↗",
    linkUrl: "https://aws.amazon.com/bedrock/",
    placeholder: "Paste AWS_ACCESS_KEY_ID (AKIA...)",
    models: [
      { value: "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0", label: "Bedrock: Claude 3.5 Haiku" },
      { value: "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", label: "Bedrock: Claude 3.5 Sonnet v2" },
    ]
  },
  ollama: {
    label: "Local Ollama Endpoint",
    linkText: "Ollama Docs ↗",
    linkUrl: "https://ollama.ai",
    placeholder: "Local execution on localhost:11434 (no key needed)",
    models: [
      { value: "ollama/llama3.2", label: "Ollama: Llama 3.2 (Local On-Prem)" },
      { value: "ollama/mistral", label: "Ollama: Mistral 7B (Local On-Prem)" },
      { value: "ollama/qwen2.5", label: "Ollama: Qwen 2.5 (Local On-Prem)" },
    ]
  }
};

function updateProviderUI(provider) {
  const meta = PROVIDER_METADATA[provider] || PROVIDER_METADATA.gemini;
  if (apiKeyLabelText) apiKeyLabelText.textContent = meta.label;
  if (apiKeyPortalLink) {
    apiKeyPortalLink.textContent = meta.linkText;
    apiKeyPortalLink.href = meta.linkUrl;
  }
  if (geminiApiKeyInput) {
    geminiApiKeyInput.placeholder = meta.placeholder;
  }
  if (geminiModelSelect) {
    geminiModelSelect.innerHTML = "";
    meta.models.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.value;
      opt.textContent = m.label;
      geminiModelSelect.appendChild(opt);
    });
  }
}

// Stepper Elements
const stepItems = [
  document.getElementById("stepDiscovery"),
  document.getElementById("stepExtraction"),
  document.getElementById("stepNormalisation"),
  document.getElementById("stepSanitisation"),
  document.getElementById("stepDeduplication"),
  document.getElementById("stepExport")
];

// Metrics
const metricTotal = document.getElementById("metricTotal");
const metricLtb = document.getElementById("metricLtb");
const metricEol = document.getElementById("metricEol");
const metricEos = document.getElementById("metricEos");

// Filter Pills
const categoryPillButtons = document.querySelectorAll("#categoryPillContainer .pill");
const stagePillButtons = document.querySelectorAll("#stagePillContainer .pill");
const sectorPillButtons = document.querySelectorAll("#sectorFilterGroup .sector-pill");

// Initialization
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  fetchInitialData();
  fetchServerStatus();
  fetchVendorsList();
});

function setupEventListeners() {
  // Vendor Preset Dropdown
  if (vendorPresetSelect) {
    vendorPresetSelect.addEventListener("change", () => {
      const selectedId = vendorPresetSelect.value;
      const vendor = enterpriseVendors.find(v => v.id === selectedId);
      if (vendor && vendor.entry_points && vendor.entry_points.length > 0) {
        targetUrlInput.value = vendor.entry_points[0];
      } else if (vendor && vendor.website) {
        targetUrlInput.value = vendor.website;
      }
    });
  }

  // Sector Pills in Config
  sectorPillButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      sectorPillButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeSector = btn.getAttribute("data-sector");
      populateVendorDropdown();
    });
  });

  // Search
  searchInput.addEventListener("input", () => {
    clearSearchBtn.style.display = searchInput.value ? "block" : "none";
    applyFilters();
  });

  clearSearchBtn.addEventListener("click", () => {
    searchInput.value = "";
    clearSearchBtn.style.display = "none";
    applyFilters();
  });

  // Stage Pills (Rule 2: 1 record per stage)
  stagePillButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      stagePillButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeStage = btn.getAttribute("data-stage");
      applyFilters();
    });
  });

  // Category Pills
  categoryPillButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      categoryPillButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeCategory = btn.getAttribute("data-category");
      applyFilters();
    });
  });

  // Table Column Sorting
  document.querySelectorAll(".products-table th[data-sort]").forEach(th => {
    th.addEventListener("click", () => {
      const field = th.getAttribute("data-sort");
      if (sortField === field) {
        sortAscending = !sortAscending;
      } else {
        sortField = field;
        sortAscending = true;
      }
      updateSortHeaders();
      applyFilters();
    });
  });

  // Config visibility toggle
  toggleConfigBtn.addEventListener("click", () => {
    const isHidden = configGrid.style.display === "none";
    configGrid.style.display = isHidden ? "grid" : "none";
    toggleConfigBtn.textContent = isHidden ? "Hide Options" : "Show Options";
  });

  // AI Provider dropdown change
  if (aiProviderSelect) {
    aiProviderSelect.addEventListener("change", () => {
      updateProviderUI(aiProviderSelect.value);
    });
  }

  // Key auto-detection on paste or input
  if (geminiApiKeyInput) {
    geminiApiKeyInput.addEventListener("input", () => {
      const val = geminiApiKeyInput.value.trim();
      if (val.startsWith("sk-ant-") && aiProviderSelect && aiProviderSelect.value !== "anthropic") {
        aiProviderSelect.value = "anthropic";
        updateProviderUI("anthropic");
      } else if ((val.startsWith("sk-") || val.startsWith("sess-")) && aiProviderSelect && aiProviderSelect.value !== "openai") {
        aiProviderSelect.value = "openai";
        updateProviderUI("openai");
      } else if (val.startsWith("AIza") && aiProviderSelect && aiProviderSelect.value !== "gemini") {
        aiProviderSelect.value = "gemini";
        updateProviderUI("gemini");
      } else if ((val.startsWith("AKIA") || val.startsWith("ASIA")) && aiProviderSelect && aiProviderSelect.value !== "bedrock") {
        aiProviderSelect.value = "bedrock";
        updateProviderUI("bedrock");
      }
    });
  }

  // Toggle API Key visibility
  toggleApiKeyVisibility.addEventListener("click", () => {
    geminiApiKeyInput.type = geminiApiKeyInput.type === "password" ? "text" : "password";
  });

  // Test Universal AI API Key Button
  const testKeyBtn = document.getElementById("testKeyBtn");
  const keyValidationStatus = document.getElementById("keyValidationStatus");
  if (testKeyBtn) {
    testKeyBtn.addEventListener("click", async () => {
      const apiKey = geminiApiKeyInput.value.trim();
      const model = geminiModelSelect.value;
      const provider = aiProviderSelect ? aiProviderSelect.value : "gemini";
      if (!apiKey && provider !== "ollama") {
        keyValidationStatus.style.display = "block";
        keyValidationStatus.style.color = "var(--accent-rose)";
        keyValidationStatus.textContent = "Please paste an API key first.";
        return;
      }
      testKeyBtn.disabled = true;
      testKeyBtn.textContent = "...";
      keyValidationStatus.style.display = "block";
      keyValidationStatus.style.color = "var(--accent-cyan)";
      keyValidationStatus.textContent = `Testing key with ${provider.toUpperCase()} engine...`;

      try {
        const res = await fetch("/api/test-key", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider: provider, api_key: apiKey, model: model, save: true })
        });
        const data = await res.json();
        if (data.success) {
          keyValidationStatus.style.color = "var(--accent-emerald)";
          keyValidationStatus.textContent = `✓ ${provider.toUpperCase()} verified & saved! Engine active.`;
          document.getElementById("geminiStatusPill").style.borderColor = "#10b981";
          if (geminiModelLabel) {
            geminiModelLabel.textContent = `${provider.toUpperCase()}: ${data.model || model}`;
          }
        } else {
          keyValidationStatus.style.color = "var(--accent-rose)";
          keyValidationStatus.textContent = `✗ ${data.message}`;
        }
      } catch (err) {
        keyValidationStatus.style.color = "var(--accent-rose)";
        keyValidationStatus.textContent = `✗ Error: ${err.message}`;
      } finally {
        testKeyBtn.disabled = false;
        testKeyBtn.textContent = "Test";
      }
    });
  }

  // Trigger Crawl Button
  triggerCrawlBtn.addEventListener("click", runLiveCrawl);

  // Export buttons
  document.getElementById("exportCsvBtn").addEventListener("click", () => {
    window.location.href = "/api/export/csv";
  });

  document.getElementById("exportJsonBtn").addEventListener("click", () => {
    window.location.href = "/api/export/json";
  });

  // Comparison Modal
  if (openComparisonBtn) {
    openComparisonBtn.addEventListener("click", openComparisonModal);
  }
  if (closeComparisonBtn) {
    closeComparisonBtn.addEventListener("click", closeComparisonModal);
  }
  if (comparisonModal) {
    comparisonModal.addEventListener("click", (e) => {
      if (e.target === comparisonModal) closeComparisonModal();
    });
  }

  // Detail Modal close
  closeModalBtn.addEventListener("click", closeModal);
  detailModal.addEventListener("click", (e) => {
    if (e.target === detailModal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeModal();
      closeComparisonModal();
    }
  });
}

async function fetchVendorsList() {
  try {
    const res = await fetch("/api/vendors");
    if (res.ok) {
      const data = await res.json();
      enterpriseVendors = data.vendors || [];
      populateVendorDropdown();
    }
  } catch (err) {
    console.warn("Could not load vendor list:", err);
  }
}

function populateVendorDropdown() {
  if (!vendorPresetSelect) return;
  vendorPresetSelect.innerHTML = "";

  const filtered = enterpriseVendors.filter(v => {
    if (activeSector === "ALL") return true;
    return (v.sector || "").toUpperCase() === activeSector.toUpperCase();
  });

  filtered.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v.id;
    opt.textContent = `[${v.sector || 'OT'}] ${v.name}`;
    if (v.id === "mitsubishi") opt.selected = true;
    vendorPresetSelect.appendChild(opt);
  });

  // Set initial URL if Mitsubishi exists
  const mitsu = enterpriseVendors.find(v => v.id === "mitsubishi");
  if (mitsu && mitsu.entry_points && mitsu.entry_points.length > 0) {
    targetUrlInput.value = mitsu.entry_points[0];
  }
}

async function fetchServerStatus() {
  try {
    const res = await fetch("/api/status");
    if (res.ok) {
      const data = await res.json();
      const provName = (data.provider || "AI").toUpperCase();
      const modName = data.model || data.gemini_model || "Flash";
      if (geminiModelLabel) {
        geminiModelLabel.textContent = `${provName}: ${modName}`;
      }
      if (data.provider && aiProviderSelect) {
        aiProviderSelect.value = data.provider;
        updateProviderUI(data.provider);
      }
      if (data.model && geminiModelSelect) {
        geminiModelSelect.value = data.model;
      }
      if (data.ai_configured || data.gemini_configured || data.openai_configured || data.anthropic_configured || data.azure_configured || data.bedrock_configured) {
        document.getElementById("geminiStatusPill").style.borderColor = "#10b981";
      }
    }
  } catch (err) {
    console.warn("Could not check server status", err);
  }
}

async function fetchInitialData() {
  try {
    resultsCount.textContent = "Loading multi-vendor product stage records...";
    const res = await fetch("/api/products");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    rawProducts = data.products || [];
    calculateMetrics(rawProducts);
    applyFilters();
  } catch (err) {
    console.error("Failed to load products:", err);
    resultsCount.textContent = "Failed to load cached products. Click 'Run AI Crawler'.";
  }
}

function calculateMetrics(products) {
  metricTotal.textContent = products.length;

  const ltbCount = products.filter(p => (p.stage || "").toLowerCase().includes("last time buy") || (p.stage || "").toLowerCase().includes("ltb")).length;
  metricLtb.textContent = ltbCount;

  const eolCount = products.filter(p => (p.stage || "").toLowerCase().includes("end of life") || (p.stage || "").toLowerCase().includes("eol")).length;
  metricEol.textContent = eolCount;

  const eosCount = products.filter(p => (p.stage || "").toLowerCase().includes("end of service") || (p.stage || "").toLowerCase().includes("eos") || (p.stage || "").toLowerCase().includes("repair")).length;
  metricEos.textContent = eosCount;
}

function applyFilters() {
  const query = searchInput.value.trim().toLowerCase();

  filteredProducts = rawProducts.filter(p => {
    // Stage Filter (Rule 2: 1 record per stage)
    if (activeStage !== "ALL") {
      const stageLower = (p.stage || "").toLowerCase();
      if (activeStage === "LTB" && !stageLower.includes("last time buy") && !stageLower.includes("ltb")) return false;
      if (activeStage === "EOL" && !stageLower.includes("end of life") && !stageLower.includes("eol")) return false;
      if (activeStage === "EOS" && !stageLower.includes("end of service") && !stageLower.includes("eos")) return false;
    }

    // Category match
    if (activeCategory !== "ALL") {
      const cat = (p.product_category || "").toUpperCase();
      const mod = (p.model_name || "").toUpperCase();
      if (activeCategory === "PLC" && !cat.includes("PLC") && !mod.includes("FX") && !mod.includes("Q") && !mod.includes("S7")) return false;
      if (activeCategory === "MELIPC" && !cat.includes("INDUSTRIAL PC") && !cat.includes("MELIPC") && !mod.includes("MI")) return false;
      if (activeCategory === "HMI" && !cat.includes("HMI") && !mod.includes("GOT") && !mod.includes("GT") && !mod.includes("PANEL")) return false;
      if (activeCategory === "Inverter" && !cat.includes("INVERTER") && !mod.includes("FR-") && !mod.includes("FREQROL") && !mod.includes("SINAMICS")) return false;
      if (activeCategory === "Motion" && !cat.includes("MOTION") && !mod.includes("LD77") && !mod.includes("MR-")) return false;
      if (activeCategory === "Robot" && !cat.includes("ROBOT") && !mod.includes("MELFA") && !mod.includes("RV-")) return false;
      if (activeCategory === "Software" && !cat.includes("SOFTWARE") && !mod.includes("OPC") && !mod.includes("SW")) return false;
    }

    // Search query match (checks vendor, model, os, firmware, stage, date, metadata)
    if (query) {
      const meta = p.metadata || {};
      const haystack = [
        p.vendor_name,
        p.model_name,
        p.product_category,
        p.os,
        p.firmware,
        p.stage,
        p.stage_date_utc,
        meta.replacement,
        meta.family,
        meta.series,
        meta.part_number,
        meta.bulletin_title,
        meta.source_url,
        meta.notes
      ].join(" ").toLowerCase();

      if (!haystack.includes(query)) return false;
    }

    return true;
  });

  // Sort
  filteredProducts.sort((a, b) => {
    let valA = a[sortField] || "";
    let valB = b[sortField] || "";
    if (typeof valA === "string") valA = valA.toLowerCase();
    if (typeof valB === "string") valB = valB.toLowerCase();

    if (valA < valB) return sortAscending ? -1 : 1;
    if (valA > valB) return sortAscending ? 1 : -1;
    return 0;
  });

  renderTable();
}

function updateSortHeaders() {
  document.querySelectorAll(".products-table th[data-sort]").forEach(th => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.getAttribute("data-sort") === sortField) {
      th.classList.add(sortAscending ? "sorted-asc" : "sorted-desc");
    }
  });
}

function renderTable() {
  tableBody.innerHTML = "";
  resultsCount.textContent = `Showing ${filteredProducts.length} of ${rawProducts.length} stage records`;

  if (filteredProducts.length === 0) {
    emptyState.style.display = "block";
    return;
  }
  emptyState.style.display = "none";

  filteredProducts.forEach((p, idx) => {
    const tr = document.createElement("tr");
    tr.addEventListener("click", () => openDetailModal(p));

    const statusVal = p.status || p.vendor_status || p.stage || "Discontinued";
    const meta = p.metadata || {};
    const sourceUrl = p.source_url || meta.source_url || "";
    const replacementVal = p.replacement || meta.replacement || "Consult Representative";
    const categoryVal = p.category || p.product_category || "General Automation";

    // Status Badge formatting
    let badgeClass = "badge-eos";
    const statusLower = statusVal.toLowerCase();
    if (statusLower.includes("last time buy") || statusLower.includes("ltb")) {
      badgeClass = "badge-ltb";
    } else if (statusLower.includes("end of life") || statusLower.includes("eol") || statusLower.includes("discontinued")) {
      badgeClass = "badge-eol";
    }

    // UTC Date formatting
    const rawUtcDate = p.stage_date_utc || "N/A";
    let utcDateHtml = `<span style="color:var(--text-muted)">N/A</span>`;
    if (rawUtcDate !== "N/A") {
      const isPast = rawUtcDate.match(/^\d{4}-\d{2}-\d{2}/) && new Date(rawUtcDate) < new Date();
      const dateClass = isPast ? "date-text date-expired" : "date-text";
      utcDateHtml = `
        <span class="${dateClass}">
          ${escapeHtml(rawUtcDate)}
          <span class="utc-tag">UTC</span>
        </span>
      `;
    }

    // Source URL formatting
    let urlHtml = `<span style="color:var(--text-muted)">N/A</span>`;
    if (sourceUrl) {
      urlHtml = `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer" class="helper-link" onclick="event.stopPropagation();" title="${escapeHtml(sourceUrl)}">Visit ↗</a>`;
    }

    // Metadata column rendering
    const metaCount = Object.keys(meta).length;
    const metaHtml = `
      <div class="meta-badge" onclick="event.stopPropagation(); openDetailModal(filteredProducts[${idx}])" title="Inspect complete metadata">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15z"/></svg>
        ${metaCount} fields
      </div>
    `;

    tr.innerHTML = `
      <td><strong>${escapeHtml(p.vendor_name || 'Mitsubishi Electric')}</strong></td>
      <td class="model-cell">${escapeHtml(p.model_name)}</td>
      <td><span class="badge-stage ${badgeClass}">${escapeHtml(statusVal)}</span></td>
      <td>${utcDateHtml}</td>
      <td>${urlHtml}</td>
      <td><span class="category-tag">${escapeHtml(categoryVal)}</span></td>
      <td><span style="color:#a7f3d0; font-size:0.85rem;">${escapeHtml(replacementVal)}</span></td>
      <td><span class="tech-tag">${escapeHtml(p.os || 'N/A')}</span></td>
      <td><span class="tech-tag">${escapeHtml(p.firmware || 'All revisions')}</span></td>
      <td>${metaHtml}</td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); openDetailModal(filteredProducts[${idx}])">
          Inspect
        </button>
      </td>
    `;
    tableBody.appendChild(tr);
  });
}

function openDetailModal(product) {
  document.getElementById("modalVendor").textContent = product.vendor_name || "Vendor";
  document.getElementById("modalTitle").textContent = product.model_name;

  const meta = product.metadata || {};
  const allMilestones = meta.all_milestones || [];

  let milestonesHtml = "";
  if (allMilestones.length > 0) {
    milestonesHtml = `
      <div class="modal-field">
        <div class="modal-field-label">All Lifecycle Stages for this Model</div>
        <div class="milestones-timeline">
          ${allMilestones.map(m => `
            <div class="timeline-item">
              <strong>${escapeHtml(m.stage)}</strong>: 
              <span class="date-text">${escapeHtml(m.date_utc || m.raw_date || 'N/A')} <span class="utc-tag">UTC</span></span>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }

  const modalBody = document.getElementById("modalBody");
  modalBody.innerHTML = `
    <!-- Top Highlights Grid -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.25rem;">
      <div class="modal-field">
        <div class="modal-field-label">Vendor & Category</div>
        <div class="modal-field-value">
          <strong>${escapeHtml(product.vendor_name)}</strong> &bull; <span class="category-tag">${escapeHtml(product.product_category || 'N/A')}</span>
        </div>
      </div>
      <div class="modal-field">
        <div class="modal-field-label">This Record's Lifecycle Stage</div>
        <div class="modal-field-value">
          <strong>${escapeHtml(product.stage)}</strong> &bull; 
          <span class="date-text">${escapeHtml(product.stage_date_utc || 'N/A')} <span class="utc-tag">UTC</span></span>
        </div>
      </div>
      <div class="modal-field">
        <div class="modal-field-label">Operating System / Platform</div>
        <div class="modal-field-value"><span class="tech-tag">${escapeHtml(product.os || 'N/A')}</span></div>
      </div>
      <div class="modal-field">
        <div class="modal-field-label">Firmware / Software Revision</div>
        <div class="modal-field-value"><span class="tech-tag">${escapeHtml(product.firmware || 'All revisions')}</span></div>
      </div>
    </div>

    ${milestonesHtml}

    <!-- Structured Metadata Card (Rule 6) -->
    <div class="modal-field" style="margin-top: 1.25rem;">
      <div class="modal-field-label">Structured Metadata Dictionary</div>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; background: rgba(15,23,42,0.6); padding: 1rem; border-radius: var(--radius-md); border: 1px solid var(--border-subtle); margin-bottom: 1rem;">
        <div><strong style="color:var(--text-muted); font-size:0.75rem;">REPLACEMENT:</strong><br><span style="color:#a7f3d0;">${escapeHtml(meta.replacement || 'Consult Representative')}</span></div>
        <div><strong style="color:var(--text-muted); font-size:0.75rem;">SERIES:</strong><br>${escapeHtml(meta.series || 'N/A')}</div>
        <div><strong style="color:var(--text-muted); font-size:0.75rem;">FAMILY:</strong><br>${escapeHtml(meta.family || product.product_category || 'N/A')}</div>
        <div><strong style="color:var(--text-muted); font-size:0.75rem;">PART NUMBER:</strong><br><code>${escapeHtml(meta.part_number || product.model_name)}</code></div>
        <div><strong style="color:var(--text-muted); font-size:0.75rem;">RAW STAGE LABEL:</strong><br>${escapeHtml(meta.raw_stage_label || product.stage)}</div>
        <div><strong style="color:var(--text-muted); font-size:0.75rem;">SOURCE URL:</strong><br><a href="${meta.source_url || '#'}" target="_blank" class="helper-link">${escapeHtml((meta.source_url || 'N/A').substring(0, 32))}... ↗</a></div>
      </div>
    </div>

    ${meta.bulletin_url ? `
      <div class="modal-field">
        <div class="modal-field-label">Official Technical Document</div>
        <div class="modal-field-value">
          <a href="${meta.bulletin_url}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm link-bulletin">
            📄 Download ${escapeHtml(meta.bulletin_title || 'Technical PDF')} ↗
          </a>
        </div>
      </div>
    ` : ''}

    <!-- Full JSON Metadata Viewer -->
    <div class="modal-field">
      <div class="modal-field-label">Raw JSON Metadata</div>
      <div class="json-dump">${escapeHtml(JSON.stringify(meta, null, 2))}</div>
    </div>
  `;

  detailModal.classList.add("open");
}

function closeModal() {
  detailModal.classList.remove("open");
}

function setWorkflowStep(stepIndex) {
  // stepIndex: 1 to 6
  stepItems.forEach((el, idx) => {
    if (!el) return;
    const num = idx + 1;
    el.classList.remove("active", "completed");
    if (num < stepIndex) {
      el.classList.add("completed");
    } else if (num === stepIndex) {
      el.classList.add("active");
    }
  });

  const percentage = Math.round((stepIndex / 6) * 100);
  if (crawlerProgressFill) {
    crawlerProgressFill.style.width = `${percentage}%`;
  }
}

async function runLiveCrawl() {
  const targetUrl = targetUrlInput.value.trim();
  const apiKey = geminiApiKeyInput.value.trim();
  const model = geminiModelSelect.value;
  const isSiteCrawl = siteCrawlCheckbox ? siteCrawlCheckbox.checked : false;
  const vendorId = vendorPresetSelect ? vendorPresetSelect.value : "mitsubishi";

  triggerCrawlBtn.disabled = true;
  triggerCrawlBtn.innerHTML = `<div class="spinner"></div> Crawling...`;
  crawlerProgressContainer.style.display = "flex";

  // Step 1: Discovery & Crawling
  setWorkflowStep(1);
  crawlerProgressText.textContent = isSiteCrawl 
    ? "STEP 1/6: Crawling full website & discovering lifecycle subdomains via Crawl4AI..."
    : "STEP 1/6: Launching Crawl4AI browser to inspect vendor lifecycle page...";

  // Simulated progression timer for visible UI feedback while request is processing
  const progressTimer = setTimeout(() => {
    setWorkflowStep(2);
    crawlerProgressText.textContent = "STEP 2/6: Extracting unstructured tables, DOM nodes & Apollo props via Universal AI Extractor...";
  }, 2500);

  const progressTimer2 = setTimeout(() => {
    setWorkflowStep(3);
    crawlerProgressText.textContent = "STEP 3/6: Normalising dates to UTC ISO 8601 & translating status to English...";
  }, 5000);

  const progressTimer3 = setTimeout(() => {
    setWorkflowStep(4);
    crawlerProgressText.textContent = "STEP 4/6: Sanitising models, scrubbing cookies/nav tokens & verifying security...";
  }, 7500);

  try {
    const provider = aiProviderSelect ? aiProviderSelect.value : "gemini";
    const response = await fetch("/api/crawl", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: targetUrl,
        vendor: vendorId,
        site_crawl: isSiteCrawl,
        provider: provider,
        api_key: apiKey,
        model: model
      })
    });

    clearTimeout(progressTimer);
    clearTimeout(progressTimer2);
    clearTimeout(progressTimer3);

    setWorkflowStep(5);
    crawlerProgressText.textContent = "STEP 5/6: Executing cryptographic deduplication & upsert merge...";

    const resData = await response.json();

    if (resData.success && resData.dataset) {
      setWorkflowStep(6);
      crawlerProgressText.textContent = "STEP 6/6: Exporting master CSV & JSON (Fingerprint omitted)...";

      rawProducts = resData.dataset.products || [];
      calculateMetrics(rawProducts);
      applyFilters();

      setTimeout(() => {
        crawlerProgressText.textContent = `Completed! Processed ${rawProducts.length} stage records across all 6 steps.`;
      }, 600);

      setTimeout(() => {
        crawlerProgressContainer.style.display = "none";
      }, 5000);
    } else {
      throw new Error(resData.error || "Crawl did not return products");
    }
  } catch (err) {
    clearTimeout(progressTimer);
    clearTimeout(progressTimer2);
    clearTimeout(progressTimer3);
    console.error("Crawl failed:", err);
    crawlerProgressText.textContent = `Error during AI crawl: ${err.message}`;
  } finally {
    triggerCrawlBtn.disabled = false;
    triggerCrawlBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
      </svg>
      Run AI Crawler
    `;
  }
}

async function openComparisonModal() {
  if (!comparisonModal) return;
  comparisonModal.classList.add("open");

  if (comparisonTableContainer) {
    comparisonTableContainer.innerHTML = `<div style="padding: 2rem; text-align: center;"><div class="spinner"></div><p style="margin-top:0.5rem; color:var(--text-muted)">Loading comparison matrix from /api/comparison...</p></div>`;
  }

  try {
    const res = await fetch("/api/comparison");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderComparisonTable(data.matrix || []);
  } catch (err) {
    if (comparisonTableContainer) {
      comparisonTableContainer.innerHTML = `<p style="color:var(--accent-rose)">Failed to load comparison: ${err.message}</p>`;
    }
  }
}

function closeComparisonModal() {
  if (comparisonModal) {
    comparisonModal.classList.remove("open");
  }
}

function renderComparisonTable(matrix) {
  if (!comparisonTableContainer) return;

  let html = `
    <table class="comparison-table">
      <thead>
        <tr>
          <th>Capability Dimension</th>
          <th>Generic IDE Crawler (Scrapy / BS4)</th>
          <th>Enterprise AI Crawler (Crawl4AI + Gemini)</th>
        </tr>
      </thead>
      <tbody>
  `;

  matrix.forEach(item => {
    html += `
      <tr>
        <td class="comparison-dim">${escapeHtml(item.dimension)}</td>
        <td class="comparison-generic">
          <span class="comparison-badge badge-dim-generic">Generic / Static</span>
          <div>${escapeHtml(item.generic_crawler)}</div>
        </td>
        <td class="comparison-ai">
          <span class="comparison-badge badge-dim-ai">Enterprise AI</span>
          <div>${escapeHtml(item.ai_crawler)}</div>
        </td>
      </tr>
    `;
  });

  html += `
      </tbody>
    </table>
  `;

  comparisonTableContainer.innerHTML = html;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
