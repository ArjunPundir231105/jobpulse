// JobPulse AI — Frontend Logic

let currentSearchMode = "query"; // "query" or "resume"
let currentResults = [];
let selectedJobId = null;
let userApiKey = localStorage.getItem("gemini_api_key") || "";

document.addEventListener("DOMContentLoaded", async () => {
  await checkConfig();
  await executeSearch();
});

// ---------------- System Status & Gemini API Key ----------------

async function checkConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    const hasKey = data.has_api_key || Boolean(userApiKey);
    
    const dot = document.getElementById("key-dot");
    const label = document.getElementById("key-status-label");

    if (hasKey) {
      dot.className = "dot active";
      label.innerText = "Gemini Key Active";
    } else {
      dot.className = "dot";
      label.innerText = "Add Gemini Key";
    }

    if (userApiKey && !data.has_api_key) {
      // Sync local storage key to backend
      await fetch("/api/set-key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: userApiKey })
      });
    }
  } catch (err) {
    console.error("Config check error:", err);
  }
}

function openKeyModal() {
  document.getElementById("gemini-key-input").value = userApiKey;
  document.getElementById("key-modal").classList.add("active");
}

function closeKeyModal() {
  document.getElementById("key-modal").classList.remove("active");
}

async function saveApiKey() {
  const val = document.getElementById("gemini-key-input").value.trim();
  userApiKey = val;
  if (val) {
    localStorage.setItem("gemini_api_key", val);
  } else {
    localStorage.removeItem("gemini_api_key");
  }

  await fetch("/api/set-key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: val })
  });

  closeKeyModal();
  await checkConfig();
  executeSearch();
}

// ---------------- Search Tabs ----------------

function switchSearchTab(mode) {
  currentSearchMode = mode;
  document.getElementById("tab-query-btn").classList.toggle("active", mode === "query");
  document.getElementById("tab-resume-btn").classList.toggle("active", mode === "resume");

  document.getElementById("search-query-container").classList.toggle("active", mode === "query");
  document.getElementById("search-resume-container").classList.toggle("active", mode === "resume");
}

function setQueryAndSearch(queryText) {
  switchSearchTab("query");
  document.getElementById("search-input").value = queryText;
  executeSearch();
}

function fillSampleResume() {
  document.getElementById("resume-input").value = 
`Alex Chen — Senior Full Stack & AI Systems Engineer
Experience:
- 5+ years building distributed backend APIs in Python and Go with PostgreSQL.
- Heavy experience deploying Docker containers, Kubernetes, and model inference pipelines with PyTorch and vLLM.
- Passionate about high-throughput systems, developer tools, and remote work.`;
  executeSearch();
}

// ---------------- Search Execution ----------------

async function executeSearch() {
  const query = document.getElementById("search-input").value.trim();
  const resume = document.getElementById("resume-input").value.trim();
  const category = document.getElementById("filter-category").value;
  const remoteOnly = document.getElementById("filter-remote").checked;
  const minSalary = parseInt(document.getElementById("filter-salary").value) || 0;

  const countEl = document.getElementById("results-count");
  const aiIndicator = document.getElementById("ai-indicator");
  countEl.innerText = "Searching roles with Gemini...";

  try {
    const payload = {
      query: currentSearchMode === "query" ? query : "",
      resume_text: currentSearchMode === "resume" ? resume : "",
      category: category,
      remote_only: remoteOnly,
      min_salary: minSalary,
      api_key: userApiKey
    };

    const res = await fetch("/api/search-ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    currentResults = data.results || [];

    countEl.innerText = `Showing ${currentResults.length} matching roles`;

    if (data.used_gemini) {
      aiIndicator.classList.remove("hidden");
    } else {
      aiIndicator.classList.add("hidden");
    }

    renderJobList();

    // Select the first job if none selected
    if (currentResults.length > 0) {
      selectJob(currentResults[0].job.id);
    } else {
      document.getElementById("job-detail-card").innerHTML = 
        `<div class="empty-detail">No jobs match your criteria. Try adjusting your query or filters.</div>`;
    }
  } catch (err) {
    console.error("Search failed:", err);
    countEl.innerText = "Search failed. Please try again.";
  }
}

// ---------------- Rendering ----------------

function renderJobList() {
  const container = document.getElementById("jobs-list");
  container.innerHTML = "";

  if (currentResults.length === 0) {
    container.innerHTML = `<div class="empty-detail">No jobs found matching your filters.</div>`;
    return;
  }

  currentResults.forEach(item => {
    const job = item.job;
    const isSelected = job.id === selectedJobId;

    const card = document.createElement("div");
    card.className = `job-card ${isSelected ? 'active' : ''}`;
    card.onclick = () => selectJob(job.id);

    const salaryFormatted = job.salary_min 
      ? `$${(job.salary_min / 1000).toFixed(0)}k – $${(job.salary_max / 1000).toFixed(0)}k` 
      : "Competitive";

    card.innerHTML = `
      <div class="card-top">
        <div>
          <div class="card-title">${job.title}</div>
          <div class="card-company">${job.company} • ${job.location}</div>
        </div>
        <div class="match-dial">${item.match_score}% Match</div>
      </div>

      <div class="card-reasoning">
        <strong>✦ Why this fits:</strong> ${item.ai_reasoning}
      </div>

      <div class="card-meta">
        <span class="card-salary">${salaryFormatted}</span>
        <div class="card-tags">
          ${(job.tags || []).slice(0, 3).map(t => `<span class="tag-badge">${t}</span>`).join("")}
        </div>
      </div>
    `;

    container.appendChild(card);
  });
}

function selectJob(jobId) {
  selectedJobId = jobId;
  
  // Highlight active card
  document.querySelectorAll(".job-card").forEach(c => c.classList.remove("active"));
  renderJobList();

  const item = currentResults.find(r => r.job.id === jobId);
  if (!item) return;

  const job = item.job;
  const detailContainer = document.getElementById("job-detail-card");

  const salaryFormatted = job.salary_min 
    ? `$${job.salary_min.toLocaleString()} – $${job.salary_max.toLocaleString()} USD` 
    : "Competitive compensation";

  detailContainer.innerHTML = `
    <div class="detail-header">
      <h2 class="detail-title">${job.title}</h2>
      <div class="detail-company">
        <strong>${job.company}</strong> • <span>${job.location}</span>
      </div>

      <div class="detail-grid">
        <div class="detail-stat">
          <label>Salary Range</label>
          <span>${salaryFormatted}</span>
        </div>
        <div class="detail-stat">
          <label>Workplace</label>
          <span>${job.is_remote ? 'Remote-first' : 'In-office / Hybrid'}</span>
        </div>
        <div class="detail-stat">
          <label>Experience</label>
          <span>${job.experience_level || 'Mid-Senior'}</span>
        </div>
        <div class="detail-stat">
          <label>Category</label>
          <span>${job.category}</span>
        </div>
      </div>
    </div>

    <div class="detail-section">
      <h4>About the Role</h4>
      <p class="detail-desc">${job.description}</p>
    </div>

    <div class="detail-section">
      <h4>Requirements</h4>
      <ul class="requirements-list">
        ${(job.requirements || []).map(r => `<li>${r}</li>`).join("")}
      </ul>
    </div>

    <div class="detail-section">
      <h4>Tech Stack & Keywords</h4>
      <div class="card-tags" style="margin-top:0.4rem;">
        ${(job.tags || []).map(t => `<span class="tag-badge" style="font-size:0.8rem; padding:4px 8px;">${t}</span>`).join("")}
      </div>
    </div>

    <!-- AI Pitch / Cover Letter Tool -->
    <div class="ai-pitch-box">
      <h4>✦ Draft Tailored Application Pitch with Gemini</h4>
      <textarea id="pitch-notes" class="pitch-textarea" rows="2" placeholder="Optional notes: e.g. 'I built a similar container pipeline at my last job...'"></textarea>
      <button class="btn-pitch" onclick="generateCoverLetter('${job.id}')">Generate Pitch with Gemini</button>
      <div id="pitch-result" class="pitch-output" style="display:none;"></div>
    </div>
  `;
}

// ---------------- AI Cover Letter ----------------

async function generateCoverLetter(jobId) {
  const notes = document.getElementById("pitch-notes").value.trim();
  const btn = event.target;
  const outputBox = document.getElementById("pitch-result");

  btn.innerText = "Drafting with Gemini...";
  btn.disabled = true;

  try {
    const res = await fetch("/api/generate-cover-letter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: jobId,
        user_notes: notes,
        api_key: userApiKey
      })
    });

    const data = await res.json();
    outputBox.style.display = "block";
    outputBox.innerText = data.cover_letter;
  } catch (err) {
    outputBox.style.display = "block";
    outputBox.innerText = "Error generating cover letter. Please verify your Gemini API key.";
  } finally {
    btn.innerText = "Generate Pitch with Gemini";
    btn.disabled = false;
  }
}
