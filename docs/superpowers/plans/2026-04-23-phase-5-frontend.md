# Phase 5 Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete Phase 5 frontend shell and QR-code support so the product can be used end-to-end through the browser.

**Architecture:** Replace the placeholder page with a single-page shell composed of a left control drawer, central search/results stage, and right detail panel. Add one backend route for QR-code generation, then wire the frontend to existing APIs for folders, search, indexing, model downloads, and image viewing using framework-free JavaScript.

**Tech Stack:** FastAPI, unittest, plain HTML/CSS/JavaScript, existing PhotoFinder API routes

---

## File Structure

- Create: `web/style.css`
  - Owns layout, design tokens, component styling, responsive behavior, and transitions.
- Create: `web/app.js`
  - Owns state, API helpers, polling, rendering, and event wiring.
- Modify: `web/index.html`
  - Replace the Phase 1 placeholder with the Phase 5 application shell and script/style references.
- Modify: `api/routes/system.py`
  - Add `GET /api/system/qrcode` and any helper needed to render a PNG from the LAN URL.
- Modify: `api/app.py`
  - Ensure static assets required by `style.css` and `app.js` remain served correctly.
- Modify: `api/schemas.py`
  - Add response models only if the QR-code route needs them; otherwise keep the route binary.
- Modify: `tests/test_system_routes.py`
  - Add QR-code route tests.

### Task 1: Lock QR-code backend behavior with tests

**Files:**
- Modify: `tests/test_system_routes.py`
- Modify: `api/routes/system.py`

- [ ] **Step 1: Write the failing tests for the QR-code route**

```python
    def test_system_qrcode_returns_png_bytes(self) -> None:
        app = create_app()

        with mock.patch("api.routes.system.get_lan_url", return_value="http://192.168.1.8:7700"):
            response = TestClient(app).get("/api/system/qrcode")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_system_qrcode_returns_503_when_lan_url_missing(self) -> None:
        app = create_app()

        with mock.patch("api.routes.system.get_lan_url", return_value=None):
            response = TestClient(app).get("/api/system/qrcode")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "LAN URL is unavailable for QR code generation"},
        )
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
./.venv/bin/python -m unittest tests.test_system_routes.SystemRouteTests.test_system_qrcode_returns_png_bytes tests.test_system_routes.SystemRouteTests.test_system_qrcode_returns_503_when_lan_url_missing -v
```

Expected: FAIL because `/api/system/qrcode` does not exist yet.

- [ ] **Step 3: Add the minimal QR-code implementation**

```python
import io

import qrcode
from fastapi import HTTPException
from fastapi.responses import Response


@router.get("/qrcode")
async def get_system_qrcode(request: Request) -> Response:
    lan_url = get_lan_url(request.url.port or config.DEFAULT_PORT)
    if not lan_url:
        raise HTTPException(status_code=503, detail="LAN URL is unavailable for QR code generation")

    image = qrcode.make(lan_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")
```

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
./.venv/bin/python -m unittest tests.test_system_routes.SystemRouteTests.test_system_qrcode_returns_png_bytes tests.test_system_routes.SystemRouteTests.test_system_qrcode_returns_503_when_lan_url_missing -v
```

Expected: PASS

### Task 2: Replace the placeholder HTML with the Phase 5 shell

**Files:**
- Modify: `web/index.html`

- [ ] **Step 1: Write the failing shell smoke test expectation**

Add to the existing frontend smoke coverage:

```python
        response = client.get("/web/index.html")

        self.assertIn("photofinder-app", response.text)
        self.assertIn("/web/style.css", response.text)
        self.assertIn("/web/app.js", response.text)
        self.assertIn("left-drawer", response.text)
        self.assertIn("detail-panel", response.text)
```

- [ ] **Step 2: Run the frontend smoke test to verify it fails**

Run:

```bash
./.venv/bin/python -m unittest tests.test_phase1.Phase1SmokeTests.test_static_index_serves_successfully -v
```

Expected: FAIL because the placeholder page does not contain the new shell markers.

- [ ] **Step 3: Replace `web/index.html` with the application shell**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>PhotoFinder</title>
    <link rel="stylesheet" href="/web/style.css" />
  </head>
  <body>
    <div id="photofinder-app" class="app-shell">
      <aside id="left-drawer" class="left-drawer">
        <div class="drawer-header">
          <p class="eyebrow">PhotoFinder</p>
          <h1>Search Your Photos</h1>
        </div>
        <section id="library-card" class="panel-card"></section>
        <section id="models-card" class="panel-card"></section>
        <section id="indexing-card" class="panel-card"></section>
        <section id="device-card" class="panel-card"></section>
      </aside>

      <main class="stage">
        <header class="stage-header">
          <button id="drawer-toggle" class="mobile-only" type="button">Menu</button>
          <label class="search-shell" for="search-input">
            <span>Search</span>
            <input id="search-input" type="search" placeholder="Try dog, sunset, 森林, 日落" />
          </label>
          <p id="rewritten-query" class="rewritten-query" hidden></p>
        </header>

        <section id="status-banner" class="status-banner" hidden></section>
        <section id="results-meta" class="results-meta"></section>
        <section id="empty-state" class="empty-state"></section>
        <section id="results-grid" class="results-grid"></section>
      </main>

      <aside id="detail-panel" class="detail-panel">
        <div id="detail-content" class="detail-content"></div>
      </aside>
    </div>

    <script type="module" src="/web/app.js"></script>
  </body>
</html>
```

- [ ] **Step 4: Run the shell smoke test to verify it passes**

Run:

```bash
./.venv/bin/python -m unittest tests.test_phase1.Phase1SmokeTests.test_static_index_serves_successfully -v
```

Expected: PASS

### Task 3: Add the complete Phase 5 stylesheet

**Files:**
- Create: `web/style.css`
- Modify: `web/index.html`

- [ ] **Step 1: Write a failing static asset smoke test**

Add assertions like:

```python
        css_response = client.get("/web/style.css")
        self.assertEqual(css_response.status_code, 200)
        self.assertIn("--bg-base", css_response.text)
        self.assertIn(".left-drawer", css_response.text)
        self.assertIn("@media (max-width: 960px)", css_response.text)
```

- [ ] **Step 2: Run the smoke test to verify it fails**

Run:

```bash
./.venv/bin/python -m unittest tests.test_phase1.Phase1SmokeTests.test_static_index_serves_successfully -v
```

Expected: FAIL because `/web/style.css` does not exist.

- [ ] **Step 3: Create the stylesheet with tokens, layout, and responsive behavior**

```css
:root {
  --bg-base: #0d1117;
  --bg-elevated: rgba(20, 24, 32, 0.88);
  --bg-panel: rgba(15, 18, 25, 0.94);
  --line-soft: rgba(255, 255, 255, 0.08);
  --text-strong: #f7f4ee;
  --text-muted: #9ea7b8;
  --accent: #f38b54;
  --accent-soft: rgba(243, 139, 84, 0.16);
  --shadow-xl: 0 30px 80px rgba(0, 0, 0, 0.42);
  --radius-lg: 24px;
}

body {
  margin: 0;
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(243, 139, 84, 0.18), transparent 28%),
    radial-gradient(circle at bottom right, rgba(73, 144, 226, 0.12), transparent 24%),
    var(--bg-base);
  color: var(--text-strong);
}

.app-shell {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr) 360px;
  min-height: 100vh;
}

.left-drawer,
.detail-panel {
  background: var(--bg-panel);
  border-right: 1px solid var(--line-soft);
  backdrop-filter: blur(18px);
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 18px;
}

@media (max-width: 960px) {
  .app-shell {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 4: Run the static asset smoke test to verify it passes**

Run:

```bash
./.venv/bin/python -m unittest tests.test_phase1.Phase1SmokeTests.test_static_index_serves_successfully -v
```

Expected: PASS

### Task 4: Add frontend app state, rendering, and API wiring

**Files:**
- Create: `web/app.js`

- [ ] **Step 1: Write a failing static asset smoke test for the app script**

Add assertions like:

```python
        js_response = client.get("/web/app.js")
        self.assertEqual(js_response.status_code, 200)
        self.assertIn("const state =", js_response.text)
        self.assertIn("async function bootstrap()", js_response.text)
        self.assertIn("async function searchPhotos(query)", js_response.text)
```

- [ ] **Step 2: Run the smoke test to verify it fails**

Run:

```bash
./.venv/bin/python -m unittest tests.test_phase1.Phase1SmokeTests.test_static_index_serves_successfully -v
```

Expected: FAIL because `/web/app.js` does not exist.

- [ ] **Step 3: Create the minimal but complete app controller**

```javascript
const state = {
  systemInfo: null,
  folders: [],
  indexStatus: null,
  downloadStatus: null,
  searchQuery: "",
  rewrittenQuery: "",
  searchResults: [],
  selectedPhoto: null,
  fatalError: "",
  polling: { indexTimer: null, downloadTimer: null },
};

async function apiGet(path) {
  const response = await fetch(path);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function bootstrap() {
  try {
    const [systemInfo, folders, indexStatus, downloadStatus] = await Promise.all([
      apiGet("/api/system/info"),
      apiGet("/api/library/folders"),
      apiGet("/api/index/status"),
      apiGet("/api/models/download/status"),
    ]);
    state.systemInfo = systemInfo;
    state.folders = folders.folders;
    state.indexStatus = indexStatus;
    state.downloadStatus = downloadStatus;
    renderApp();
    startPollingIfNeeded();
  } catch (error) {
    state.fatalError = error.message;
    renderApp();
  }
}

async function searchPhotos(query) {
  if (!query.trim()) {
    state.searchResults = [];
    state.rewrittenQuery = "";
    renderApp();
    return;
  }
  const payload = await apiGet(`/api/search?q=${encodeURIComponent(query)}`);
  state.searchResults = payload.results;
  state.rewrittenQuery = payload.rewritten_query || "";
  state.selectedPhoto = payload.results[0] || null;
  renderApp();
}

bootstrap();
```

- [ ] **Step 4: Run the smoke test to verify it passes**

Run:

```bash
./.venv/bin/python -m unittest tests.test_phase1.Phase1SmokeTests.test_static_index_serves_successfully -v
```

Expected: PASS

### Task 5: Complete left drawer flows and progress polling

**Files:**
- Modify: `web/app.js`
- Modify: `web/index.html`

- [ ] **Step 1: Extend the smoke test to assert UI markers for Phase 5 cards**

Add assertions like:

```python
        self.assertIn("library-card", response.text)
        self.assertIn("models-card", response.text)
        self.assertIn("indexing-card", response.text)
        self.assertIn("device-card", response.text)
```

- [ ] **Step 2: Run the smoke test to verify it still passes before behavior work**

Run:

```bash
./.venv/bin/python -m unittest tests.test_phase1.Phase1SmokeTests.test_static_index_serves_successfully -v
```

Expected: PASS

- [ ] **Step 3: Expand `web/app.js` to support drawer actions and polling**

```javascript
async function openFolderPicker() {
  const payload = await apiGet("/api/system/open-folder");
  if (!payload.path) {
    throw new Error(payload.error || "Folder selection failed");
  }
  await fetch("/api/library/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: payload.path }),
  });
  await refreshFolders();
  await refreshIndexStatus();
  startPollingIfNeeded();
}

function startPollingIfNeeded() {
  stopPolling();
  if (state.indexStatus?.is_running) {
    state.polling.indexTimer = window.setInterval(refreshIndexStatus, 2000);
  }
  if (state.downloadStatus?.downloading) {
    state.polling.downloadTimer = window.setInterval(refreshDownloadStatus, 1500);
  }
}

function stopPolling() {
  if (state.polling.indexTimer) {
    window.clearInterval(state.polling.indexTimer);
    state.polling.indexTimer = null;
  }
  if (state.polling.downloadTimer) {
    window.clearInterval(state.polling.downloadTimer);
    state.polling.downloadTimer = null;
  }
}
```

- [ ] **Step 4: Run the core backend suite to verify the frontend work did not break static serving**

Run:

```bash
./.venv/bin/python -m unittest tests.test_phase1 tests.test_system_routes tests.test_search_routes tests.test_image_routes -v
```

Expected: PASS

### Task 6: Complete rendering for empty state, results grid, rewritten query, and detail panel

**Files:**
- Modify: `web/app.js`
- Modify: `web/style.css`

- [ ] **Step 1: Keep the existing API tests green before final UI rendering**

Run:

```bash
./.venv/bin/python -m unittest tests.test_search_routes tests.test_image_routes tests.test_system_routes -v
```

Expected: PASS

- [ ] **Step 2: Implement the render functions for the main user-visible states**

```javascript
function renderApp() {
  renderBanner();
  renderDrawer();
  renderResults();
  renderDetailPanel();
}

function renderResults() {
  const rewrittenNode = document.getElementById("rewritten-query");
  rewrittenNode.hidden = !state.rewrittenQuery;
  rewrittenNode.textContent = state.rewrittenQuery
    ? `Chinese query rewritten as: ${state.rewrittenQuery}`
    : "";

  const emptyNode = document.getElementById("empty-state");
  const gridNode = document.getElementById("results-grid");

  if (!state.folders.length) {
    emptyNode.innerHTML = `<div class="hero-empty"><h2>Your library is empty</h2><p>Open the left drawer to add a folder and start indexing.</p></div>`;
    gridNode.innerHTML = "";
    return;
  }

  if (!state.searchResults.length && state.searchQuery.trim()) {
    emptyNode.innerHTML = `<div class="hero-empty"><h2>No matches found</h2><p>Try a different search term.</p></div>`;
    gridNode.innerHTML = "";
    return;
  }

  emptyNode.innerHTML = "";
  gridNode.innerHTML = state.searchResults
    .map(
      (photo) => `
        <button class="photo-card" data-photo-id="${photo.id}" type="button">
          <img src="${photo.thumbnail_url}" alt="${photo.filename}" loading="lazy" />
          <span>${photo.filename}</span>
        </button>
      `,
    )
    .join("");
}
```

- [ ] **Step 3: Run the full automated test suite**

Run:

```bash
./.venv/bin/python -m unittest tests.test_phase1 tests.test_phase2_imports tests.test_image_utils tests.test_scanner tests.test_schemas tests.test_network_utils tests.test_library_routes tests.test_system_routes tests.test_embedder tests.test_indexer tests.test_model_downloader tests.test_searcher tests.test_search_routes tests.test_image_routes tests.test_query_rewriter -v
```

Expected: PASS

- [ ] **Step 4: Run manual end-to-end verification**

Run:

```bash
python3 main.py
```

Expected:

- `/web/index.html` loads the Phase 5 shell
- left drawer shows folders, model state, indexing state, and device access
- adding a folder from the drawer starts indexing
- `GET /api/search?q=forest` updates the grid
- `GET /api/search?q=日落` surfaces `rewritten_query`
- clicking a result updates the right detail panel
- mobile-width browser layout collapses the side regions correctly

## Plan Self-Review

- Spec coverage: the plan covers the new frontend shell, styling, app controller, polling, rewritten-query visibility, and `GET /api/system/qrcode`
- Placeholder scan: no TODO/TBD markers remain in the tasks
- Type consistency: file names, route paths, and state field names match the Phase 5 spec and current API surface
