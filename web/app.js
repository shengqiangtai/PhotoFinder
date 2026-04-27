const state = {
  systemInfo: null,
  folders: [],
  indexStatus: null,
  modelDownloadStatus: null,
  stageView: "search",
  searchQuery: "",
  searchResults: [],
  rewrittenQuery: null,
  selectedPhotoId: null,
  bootstrapError: null,
  libraryError: null,
  searchError: null,
  settings: null,
  settingsOpen: false,
  settingsError: null,
  settingsMessage: null,
  isSearching: false,
  searchRequestId: 0,
  polling: {
    indexTimer: null,
    downloadTimer: null,
    indexInFlight: false,
    downloadInFlight: false,
    indexError: null,
    downloadError: null,
  },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatCount(value, label) {
  const count = Number.isFinite(value) ? value : 0;
  return `${count} ${label}`;
}

function summarizeFolder(folder) {
  const total = Number(folder.photo_count ?? 0);
  const indexed = Number(folder.indexed_count ?? 0);
  return `${total} photos, ${indexed} indexed`;
}

function parseRequestError(error, fallback) {
  if (error && typeof error.message === "string") {
    return error.message;
  }
  return fallback;
}

function getActiveProvider(settings = state.settings) {
  return settings?.api_provider === "voyage" ? "voyage" : "jina";
}

function getActiveMode(settings = state.settings) {
  return settings?.embedding_mode === "api" ? "api" : "local";
}

function withRelativeMatchScores(results) {
  const photos = Array.isArray(results) ? results : [];
  if (!photos.length) {
    return [];
  }
  if (photos.every((photo) => Number.isFinite(Number(photo.match_score)))) {
    return photos.map((photo) => ({ ...photo, matchScore: Math.round(Number(photo.match_score)) }));
  }

  const similarities = photos.map((photo) => Number(photo.similarity ?? 0)).filter(Number.isFinite);
  if (!similarities.length) {
    return photos.map((photo) => ({ ...photo, matchScore: 0 }));
  }

  const minSimilarity = Math.min(...similarities);
  const maxSimilarity = Math.max(...similarities);
  const range = maxSimilarity - minSimilarity;
  if (range <= 0.000001) {
    return photos.map((photo, index) => ({ ...photo, matchScore: index === 0 ? 100 : 80 }));
  }

  return photos.map((photo) => {
    const similarity = Number(photo.similarity ?? minSimilarity);
    const score = Math.round(((similarity - minSimilarity) / range) * 100);
    return {
      ...photo,
      matchScore: Math.max(0, Math.min(100, score)),
    };
  });
}

function getFolderProgress(folder) {
  const total = Number(folder.photo_count ?? 0);
  const indexed = Number(folder.indexed_count ?? 0);
  if (!Number.isFinite(total) || total <= 0) {
    return 0;
  }
  if (!Number.isFinite(indexed) || indexed <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round((indexed / total) * 100)));
}

function compactFolderPath(folderPath) {
  const rawPath = String(folderPath ?? "").trim();
  if (!rawPath) {
    return "Unknown folder";
  }

  const normalized = rawPath.replaceAll("\\", "/").replace(/\/+$/g, "");
  const homeRelative = normalized.match(/^\/Users\/[^/]+\/(.+)$/) || normalized.match(/^[A-Za-z]:\/Users\/[^/]+\/(.+)$/);
  if (homeRelative) {
    return homeRelative[1];
  }
  if (normalized.startsWith("/")) {
    return normalized.replace(/^\/+/g, "") || normalized;
  }
  return normalized;
}

function getElements() {
  return {
    folderList: document.getElementById("folder-list"),
    stageTitle: document.getElementById("stage-title"),
    stageSubtitle: document.getElementById("stage-subtitle"),
    stageContent: document.getElementById("stage-content"),
    detailBody: document.getElementById("detail-body"),
    settingsPanel: document.getElementById("settings-panel"),
  };
}

function getActivePhotos(stageView = state.stageView) {
  switch (stageView) {
    case "search":
      return state.searchResults;
    default:
      return [];
  }
}

function getSelectedPhoto() {
  return getActivePhotos().find((photo) => photo.id === state.selectedPhotoId) ?? null;
}

function getSearchSubtitle() {
  const totalPhotos = state.systemInfo?.total_photos ?? 0;
  const indexedPhotos = state.systemInfo?.indexed_photos ?? 0;
  return `Library contains ${formatCount(totalPhotos, "photo")} and ${formatCount(indexedPhotos, "indexed")}.`;
}

function mountEmptyStageScaffold() {
  const { stageContent } = getElements();
  if (!stageContent || document.getElementById("empty-library-guide")) {
    return;
  }

  stageContent.innerHTML = `
    <section class="stage-stack">
      <div id="empty-library-guide" class="empty-state hero-empty">
        <p>No photos yet.</p>
        <p>Add a folder to start browsing your library.</p>
      </div>
    </section>
  `;
}

function updateEmptyStageFeedback() {}

function updateSearchStageFeedback() {
  const searchInput = document.getElementById("search-input");
  const searchFeedback = document.getElementById("search-feedback");

  if (searchInput && searchInput.value !== state.searchQuery) {
    searchInput.value = state.searchQuery;
  }
  if (!searchFeedback) {
    return;
  }

  if (state.searchError) {
    searchFeedback.textContent = state.searchError;
  } else if (state.isSearching) {
    searchFeedback.textContent = "Searching...";
  } else if (state.rewrittenQuery) {
    searchFeedback.textContent = `Chinese query rewritten as: ${state.rewrittenQuery}`;
  } else if (state.searchQuery && !state.searchResults.length) {
    searchFeedback.textContent = "No matches found. Try another subject, place, or mood.";
  } else if (state.searchResults.length) {
    searchFeedback.textContent = `Showing ${formatCount(state.searchResults.length, "result")}.`;
  } else {
    searchFeedback.textContent = "Use the search box to find photos.";
  }
}

function getStageViewConfig(stageView = state.stageView) {
  switch (stageView) {
    case "empty":
      return {
        title: "No photos yet",
        subtitle: "Add a folder to start browsing your library.",
        mount: mountEmptyStageScaffold,
        update: updateEmptyStageFeedback,
        renderContent() {},
      };
    case "search":
    default:
      return {
        title: "Gallery",
        subtitle: getSearchSubtitle(),
        mount: mountSearchStageScaffold,
        update: updateSearchStageFeedback,
        renderContent() {
          renderSearchResultsRegion();
        },
      };
  }
}

function renderDrawer() {
  const { folderList } = getElements();
  if (!folderList) {
    return;
  }

  const folderMarkup = state.folders.length
    ? state.folders
        .map(
          (folder) => {
            const progress = getFolderProgress(folder);
            return `
            <article class="folder-card" title="${escapeHtml(folder.path)}">
              <div class="folder-card-row">
                <div class="folder-icon" aria-hidden="true"></div>
                <div class="folder-copy">
                  <p class="folder-path" title="${escapeHtml(folder.path)}"><strong>${escapeHtml(compactFolderPath(folder.path))}</strong></p>
                  <p class="folder-meta">${escapeHtml(summarizeFolder(folder))}</p>
                </div>
              </div>
              <div class="folder-progress" aria-label="${escapeHtml(progress)} percent indexed">
                <span class="folder-progress-fill" style="width: ${progress}%"></span>
              </div>
            </article>
          `;
          },
        )
        .join("")
    : `
      <div class="empty-state">
        <p>No folders added yet.</p>
      </div>
    `;
  const errorMarkup = state.libraryError
    ? `<p class="detail-line">${escapeHtml(state.libraryError)}</p>`
    : "";
  folderList.innerHTML = `${folderMarkup}${errorMarkup}`;
}

function getSettingsProviderLabel(provider) {
  return provider === "voyage" ? "Voyage AI" : "Jina AI";
}

function renderSettingsPanel() {
  const { settingsPanel } = getElements();
  if (!settingsPanel) {
    return;
  }

  const settings = state.settings;
  const mode = getActiveMode(settings);
  const provider = getActiveProvider(settings);
  const keyConfigured = provider === "voyage" ? settings?.voyage_key_configured : settings?.jina_key_configured;
  const vectorDim = settings?.vector_dim ?? (mode === "api" ? 1024 : 512);
  const visualStatus = settings?.local_model_status?.visual ?? "unknown";
  const textualStatus = settings?.local_model_status?.multilingual ?? settings?.local_model_status?.textual ?? "unknown";
  const statusMarkup = state.settingsMessage
    ? `<p class="settings-status" data-kind="ok">${escapeHtml(state.settingsMessage)}</p>`
    : state.settingsError
      ? `<p class="settings-status" data-kind="error">${escapeHtml(state.settingsError)}</p>`
      : "";

  settingsPanel.setAttribute("data-open", state.settingsOpen ? "true" : "false");
  settingsPanel.innerHTML = `
    <div class="settings-shell">
      <header class="settings-header">
        <div>
          <h2 class="settings-title">Settings</h2>
          <p class="settings-subtitle">Embedding mode and API access</p>
        </div>
        <button id="settings-close-action" class="icon-action" type="button" aria-label="Close settings" title="Close">
          Close
        </button>
      </header>

      <section class="settings-section">
        <h3 class="settings-section-title">AI model mode</h3>
        <label class="settings-option">
          <input type="radio" name="embedding-mode" value="local" ${mode === "local" ? "checked" : ""} />
          <span>Local mode</span>
        </label>
        <label class="settings-option">
          <input type="radio" name="embedding-mode" value="api" ${mode === "api" ? "checked" : ""} />
          <span>API mode</span>
        </label>
      </section>

      <section class="settings-section">
        <h3 class="settings-section-title">API provider</h3>
        <div class="settings-segment">
          <label>
            <input type="radio" name="api-provider" value="jina" ${provider === "jina" ? "checked" : ""} />
            <span>Jina AI</span>
          </label>
          <label>
            <input type="radio" name="api-provider" value="voyage" ${provider === "voyage" ? "checked" : ""} />
            <span>Voyage AI</span>
          </label>
        </div>
      </section>

      <section class="settings-section">
        <h3 class="settings-section-title">${escapeHtml(getSettingsProviderLabel(provider))} API Key</h3>
        <div class="settings-key-row">
          <input id="api-key-input" class="settings-input" type="password" autocomplete="off" placeholder="${keyConfigured ? "Configured" : "Paste API key"}" />
          <button id="api-key-save-action" class="nav-action compact-action" type="button">Verify</button>
        </div>
        <p class="settings-muted">${keyConfigured ? "Key configured" : "No key configured"}</p>
      </section>

      <section class="settings-section">
        <button id="embedding-mode-save-action" class="nav-action" type="button">Switch mode</button>
        <p class="settings-warning">Switching mode clears existing vectors and requires reindexing.</p>
      </section>

      <section class="settings-section">
        <h3 class="settings-section-title">Current index</h3>
        <p class="settings-line">Mode: ${escapeHtml(mode === "api" ? getSettingsProviderLabel(provider) : "Local CLIP")}</p>
        <p class="settings-line">Vector dim: ${escapeHtml(vectorDim)}</p>
        <p class="settings-line">Local model: visual ${escapeHtml(visualStatus)}, text ${escapeHtml(textualStatus)}</p>
        <p class="settings-line">Reindex needed: ${settings?.index_mode_mismatch || state.indexStatus?.requires_reindex ? "yes" : "no"}</p>
      </section>
      ${statusMarkup}
    </div>
  `;

  bindSettingsPanelEvents();
}

function readSelectedRadio(name, fallback) {
  const selected = document.querySelector ? document.querySelector(`input[name="${name}"]:checked`) : null;
  return selected?.value ?? fallback;
}

function bindSettingsPanelEvents() {
  const closeAction = document.getElementById("settings-close-action");
  const saveKeyAction = document.getElementById("api-key-save-action");
  const saveModeAction = document.getElementById("embedding-mode-save-action");

  if (closeAction) {
    closeAction.addEventListener("click", () => closeSettingsPanel());
  }
  if (saveKeyAction) {
    saveKeyAction.addEventListener("click", async () => saveApiKeyFromPanel());
  }
  if (saveModeAction) {
    saveModeAction.addEventListener("click", async () => switchEmbeddingModeFromPanel());
  }
}

function setPollingTimer(timerKey, shouldPoll, delay, callback) {
  const currentTimer = state.polling[timerKey];
  if (shouldPoll) {
    if (!currentTimer) {
      state.polling[timerKey] = window.setInterval(() => callback(), delay);
    }
    return;
  }

  if (currentTimer) {
    window.clearInterval(currentTimer);
    state.polling[timerKey] = null;
  }
}

function stopPolling() {
  setPollingTimer("indexTimer", false, 0, pollIndexStatus);
  setPollingTimer("downloadTimer", false, 0, pollDownloadStatus);
}

function startPollingIfNeeded() {
  setPollingTimer("indexTimer", Boolean(state.indexStatus?.is_running), 2000, pollIndexStatus);
  setPollingTimer("downloadTimer", Boolean(state.modelDownloadStatus?.downloading), 1500, pollDownloadStatus);
}

function mountSearchStageScaffold() {
  const { stageContent } = getElements();
  if (!stageContent || document.getElementById("search-form")) {
    return;
  }

  stageContent.innerHTML = `
    <section class="stage-stack">
      <form id="search-form" class="search-form">
        <input
          id="search-input"
          class="search-input"
          name="query"
          type="search"
          placeholder="Search photos"
          aria-label="Search photos"
        />
        <button id="search-submit" class="nav-action" type="submit">Search</button>
      </form>
      <p id="search-feedback" class="search-feedback"></p>
      <div id="results-region" class="results-region"></div>
    </section>
  `;

  const searchForm = document.getElementById("search-form");
  const resultsRegion = document.getElementById("results-region");
  if (searchForm) {
    searchForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = document.getElementById("search-input");
      await searchPhotos(input ? input.value : "");
    });
  }
  if (resultsRegion) {
    resultsRegion.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target.closest(".result-card-select") : null;
      if (!target) {
        return;
      }
      const photoId = Number(target.getAttribute("data-photo-id"));
      selectPhoto(photoId);
    });
    resultsRegion.addEventListener("keydown", (event) => {
      if (!(event.target instanceof Element)) {
        return;
      }
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      const target = event.target.closest(".result-card-select");
      if (!target) {
        return;
      }
      event.preventDefault();
      const photoId = Number(target.getAttribute("data-photo-id"));
      selectPhoto(photoId);
    });
  }
}

function renderSearchResultsRegion() {
  const resultsRegion = document.getElementById("results-region");
  if (!resultsRegion) {
    return;
  }

  if (!state.searchResults.length) {
    if (state.searchQuery && !state.isSearching && !state.searchError) {
      resultsRegion.innerHTML = `
        <div class="empty-state hero-empty">
          <p>No matches found.</p>
          <p>Try another subject, place, or mood.</p>
        </div>
      `;
      return;
    }

    resultsRegion.innerHTML = `
      <div class="empty-state">
        <p>Search for a subject, place, or mood to see matching photos.</p>
      </div>
    `;
    return;
  }

  resultsRegion.innerHTML = `
    <div class="results-grid">
      ${state.searchResults
        .map((photo) => {
          const isSelected = state.selectedPhotoId === photo.id;
          return `
            <article class="result-card" data-selected="${isSelected ? "true" : "false"}">
              <button
                class="result-card-select"
                type="button"
                data-photo-id="${photo.id}"
                aria-pressed="${isSelected ? "true" : "false"}"
              >
                <img
                  class="result-card-image"
                  src="${escapeHtml(photo.thumbnail_url)}"
                  alt="${escapeHtml(photo.filename)}"
                />
                <div class="result-card-body">
                  <p class="result-card-title">${escapeHtml(photo.filename)}</p>
                  <p class="result-card-meta">
                    Match ${escapeHtml(photo.matchScore ?? 0)}
                  </p>
                </div>
              </button>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function updateResultSelection() {
  const resultsRegion = document.getElementById("results-region");
  if (!resultsRegion) {
    return;
  }

  resultsRegion.querySelectorAll("[data-photo-id]").forEach((element) => {
    const photoId = Number(element.getAttribute("data-photo-id"));
    const isSelected = state.selectedPhotoId === photoId;
    element.closest(".result-card")?.setAttribute("data-selected", isSelected ? "true" : "false");
    element.setAttribute("aria-pressed", isSelected ? "true" : "false");
  });
}

function renderStage({ refreshResults = false } = {}) {
  const { stageTitle, stageSubtitle, stageContent } = getElements();
  if (!stageTitle || !stageSubtitle || !stageContent) {
    return;
  }

  if (state.bootstrapError) {
    stageTitle.textContent = "Gallery unavailable";
    stageSubtitle.textContent = "Bootstrap failed before the app could load.";
    stageContent.innerHTML = `
      <div class="empty-state">
        <p>${escapeHtml(state.bootstrapError)}</p>
      </div>
    `;
    return;
  }

  const stageView = getStageViewConfig(state.stageView);
  stageTitle.textContent = stageView.title;
  stageSubtitle.textContent = stageView.subtitle;

  stageView.mount();
  stageView.update();

  if (refreshResults) {
    stageView.renderContent();
  }
}

function renderDetailPanel() {
  const { detailBody } = getElements();
  if (!detailBody) {
    return;
  }

  const selectedPhoto = getSelectedPhoto();
  if (selectedPhoto) {
    detailBody.innerHTML = `
      <img
        class="detail-preview"
        src="${escapeHtml(selectedPhoto.full_image_url)}"
        alt="${escapeHtml(selectedPhoto.filename)}"
      />
      <p class="detail-line"><strong>${escapeHtml(selectedPhoto.filename)}</strong></p>
      <p class="detail-line">Match ${escapeHtml(selectedPhoto.matchScore ?? 0)}</p>
      <p class="detail-line">${escapeHtml(selectedPhoto.taken_at ?? "Taken date unavailable")}</p>
      <p class="detail-line">
        <a class="detail-link" href="${escapeHtml(selectedPhoto.full_image_url)}" target="_blank" rel="noopener noreferrer">
          Open original image
        </a>
      </p>
    `;
    return;
  }

  const indexStatus = state.indexStatus
    ? `${state.indexStatus.phase || "idle"} · ${state.indexStatus.processed}/${state.indexStatus.total}`
    : "idle";
  const downloadStatus = state.modelDownloadStatus?.downloading
    ? `${state.modelDownloadStatus.model} ${state.modelDownloadStatus.percent}%`
    : "No active downloads";
  const indexErrorLine = state.polling.indexError
    ? `<p class="detail-line">Indexer updates paused: ${escapeHtml(state.polling.indexError)}</p>`
    : "";
  const downloadErrorLine = state.polling.downloadError
    ? `<p class="detail-line">Download updates paused: ${escapeHtml(state.polling.downloadError)}</p>`
    : "";

  detailBody.innerHTML = `
    <p class="detail-line">Select an image to inspect its details.</p>
    <p class="detail-line">Indexer: ${escapeHtml(indexStatus)}</p>
    <p class="detail-line">Downloads: ${escapeHtml(downloadStatus)}</p>
    ${indexErrorLine}
    ${downloadErrorLine}
  `;
}

function selectPhoto(photoId) {
  state.selectedPhotoId = getActivePhotos().some((photo) => photo.id === photoId) ? photoId : null;
  updateResultSelection();
  renderDetailPanel();
}

function render() {
  renderDrawer();
  renderStage({ refreshResults: true });
  renderDetailPanel();
}

async function apiGet(path) {
  const response = await fetch(path, {
    headers: {
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`);
  }
  return response.json();
}

async function apiPost(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `Request failed for ${path}: ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.message || payload.detail || message;
    } catch (_error) {
      message = `Request failed for ${path}: ${response.status}`;
    }
    throw new Error(message);
  }
  return response.json();
}

async function refreshSettings() {
  state.settings = await apiGet("/api/settings");
  renderSettingsPanel();
}

async function refreshFolders() {
  const payload = await apiGet("/api/library/folders");
  state.folders = Array.isArray(payload.folders) ? payload.folders : [];
  renderDrawer();
}

async function refreshSystemInfo() {
  state.systemInfo = await apiGet("/api/system/info");
  state.stageView = state.systemInfo.total_photos > 0 ? "search" : "empty";
  renderStage({ refreshResults: true });
}

async function refreshIndexStatus() {
  state.indexStatus = await apiGet("/api/index/status");
  if (!state.indexStatus?.is_running) {
    await refreshSystemInfo();
  }
  renderDetailPanel();
  renderSettingsPanel();
  startPollingIfNeeded();
}

async function refreshDownloadStatus() {
  state.modelDownloadStatus = await apiGet("/api/models/download/status");
  renderDetailPanel();
  startPollingIfNeeded();
}

async function runPollingRefresh(timerKey, inFlightKey, errorKey, callback, label) {
  if (state.polling[inFlightKey]) {
    return;
  }

  state.polling[inFlightKey] = true;
  try {
    await callback();
    state.polling[errorKey] = null;
  } catch (error) {
    state.polling[errorKey] =
      error && typeof error.message === "string" ? error.message : `${label} updates failed.`;
    setPollingTimer(timerKey, false, 0, callback);
    renderDetailPanel();
  } finally {
    state.polling[inFlightKey] = false;
  }
}

async function pollIndexStatus() {
  await runPollingRefresh("indexTimer", "indexInFlight", "indexError", refreshIndexStatus, "Indexer");
}

async function pollDownloadStatus() {
  await runPollingRefresh(
    "downloadTimer",
    "downloadInFlight",
    "downloadError",
    refreshDownloadStatus,
    "Download",
  );
}

async function openFolderPicker() {
  state.libraryError = null;
  renderDrawer();
  const payload = await apiGet("/api/system/open-folder");
  const selectedPath = payload.selected_path ?? payload.path ?? null;
  if (!selectedPath || payload.cancelled) {
    return;
  }

  await apiPost("/api/library/add", { path: selectedPath });
  await refreshFolders();
  await refreshIndexStatus();
  await refreshSystemInfo();
}

async function searchPhotos(query) {
  state.searchRequestId += 1;
  const requestId = state.searchRequestId;
  state.searchQuery = query.trim();
  state.searchError = null;

  if (!state.searchQuery) {
    state.searchResults = [];
    state.rewrittenQuery = null;
    state.selectedPhotoId = null;
    state.isSearching = false;
    renderStage({ refreshResults: true });
    renderDetailPanel();
    return;
  }

  state.isSearching = true;
  state.stageView = "search";
  state.searchResults = [];
  state.rewrittenQuery = null;
  state.selectedPhotoId = null;
  renderStage({ refreshResults: true });
  renderDetailPanel();

  try {
    const payload = await apiGet(`/api/search?q=${encodeURIComponent(state.searchQuery)}`);
    if (requestId !== state.searchRequestId) {
      return;
    }
    state.searchResults = withRelativeMatchScores(payload.results);
    state.rewrittenQuery = payload.rewritten_query ?? null;
    state.selectedPhotoId = state.searchResults[0]?.id ?? null;
  } catch (error) {
    if (requestId !== state.searchRequestId) {
      return;
    }
    state.searchResults = [];
    state.rewrittenQuery = null;
    state.selectedPhotoId = null;
    state.searchError = error && typeof error.message === "string" ? error.message : "Search failed.";
  } finally {
    if (requestId !== state.searchRequestId) {
      return;
    }
    state.isSearching = false;
    renderStage({ refreshResults: true });
    renderDetailPanel();
  }
}

async function openSettingsPanel() {
  state.settingsOpen = true;
  state.settingsError = null;
  state.settingsMessage = null;
  renderSettingsPanel();
  try {
    await refreshSettings();
  } catch (error) {
    state.settingsError = parseRequestError(error, "Settings failed to load.");
    renderSettingsPanel();
  }
}

function closeSettingsPanel() {
  state.settingsOpen = false;
  renderSettingsPanel();
}

async function saveApiKeyFromPanel() {
  const provider = readSelectedRadio("api-provider", getActiveProvider());
  const input = document.getElementById("api-key-input");
  const apiKey = input ? input.value.trim() : "";
  if (!apiKey) {
    state.settingsError = "Enter an API key first.";
    state.settingsMessage = null;
    renderSettingsPanel();
    return;
  }

  state.settingsError = null;
  state.settingsMessage = "Verifying API key...";
  renderSettingsPanel();
  try {
    await apiPost("/api/settings/api-key", { provider, api_key: apiKey });
    state.settingsMessage = "API key verified.";
    await refreshSettings();
  } catch (error) {
    state.settingsError = parseRequestError(error, "API key verification failed.");
    state.settingsMessage = null;
    renderSettingsPanel();
  }
}

async function switchEmbeddingModeFromPanel() {
  const mode = readSelectedRadio("embedding-mode", getActiveMode());
  const provider = readSelectedRadio("api-provider", getActiveProvider());
  state.settingsError = null;
  state.settingsMessage = "Switching embedding mode...";
  renderSettingsPanel();
  try {
    const payload = await apiPost("/api/settings/embedding-mode", { mode, provider });
    state.settingsMessage = payload.message || "Mode switched. Reindex is required.";
    await refreshSettings();
    await refreshIndexStatus();
  } catch (error) {
    state.settingsError = parseRequestError(error, "Mode switch failed.");
    state.settingsMessage = null;
    renderSettingsPanel();
  }
}

async function bootstrap() {
  try {
    const [systemInfo, folderPayload, indexStatus, downloadStatus] = await Promise.all([
      apiGet("/api/system/info"),
      apiGet("/api/library/folders"),
      apiGet("/api/index/status"),
      apiGet("/api/models/download/status"),
    ]);

    state.systemInfo = systemInfo;
    state.folders = Array.isArray(folderPayload.folders) ? folderPayload.folders : [];
    state.indexStatus = indexStatus;
    state.modelDownloadStatus = downloadStatus;
    state.stageView = state.systemInfo.total_photos > 0 ? "search" : "empty";
    state.bootstrapError = null;
    render();
    const openFolderAction = document.getElementById("open-folder-action");
    const settingsAction = document.getElementById("settings-action");
    if (openFolderAction) {
      openFolderAction.addEventListener("click", async (event) => {
        event.preventDefault();
        try {
          await openFolderPicker();
        } catch (error) {
          state.libraryError =
            error && typeof error.message === "string" ? error.message : "Folder import failed.";
          renderDrawer();
        }
      });
    }
    if (settingsAction) {
      settingsAction.addEventListener("click", async (event) => {
        event.preventDefault();
        await openSettingsPanel();
      });
    }
    refreshSettings().catch((error) => {
      state.settingsError = parseRequestError(error, "Settings failed to load.");
      renderSettingsPanel();
    });
    startPollingIfNeeded();
  } catch (reason) {
    state.bootstrapError =
      reason && typeof reason.message === "string" ? reason.message : "Bootstrap failed.";
    render();
  }
}

window.searchPhotos = searchPhotos;
window.openFolderPicker = openFolderPicker;
window.openSettingsPanel = openSettingsPanel;
window.startPollingIfNeeded = startPollingIfNeeded;

document.addEventListener("DOMContentLoaded", () => {
  bootstrap();
});
