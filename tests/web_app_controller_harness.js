const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class FakeElement {
  constructor(id, document) {
    this.id = id;
    this.document = document;
    this.listeners = {};
    this.attributes = {};
    this._innerHTML = "";
    this.textContent = "";
    this.value = "";
    this.cards = [];
    this.children = [];
    this.parentElement = null;
  }

  set innerHTML(value) {
    this.document.replaceInnerHTML(this, value);
  }

  get innerHTML() {
    return this._innerHTML;
  }

  addEventListener(type, callback) {
    if (!this.listeners[type]) {
      this.listeners[type] = [];
    }
    this.listeners[type].push(callback);
  }

  querySelectorAll(selector) {
    const matches = [];
    const visit = (node) => {
      if (selector === "[data-photo-id]" && node.attributes["data-photo-id"]) {
        matches.push(node);
      }
      for (const child of node.children) {
        visit(child);
      }
    };
    visit(this);
    return matches;
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  async dispatchEvent(event) {
    const type = typeof event === "string" ? event : event.type;
    const callbacks = this.listeners[type] ?? [];
    for (const callback of callbacks) {
      await callback(event);
    }
    return true;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "class") {
      this.className = String(value);
    }
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  closest(selector) {
    let current = this;
    while (current) {
      if (selector === "[data-photo-id]" && current.attributes["data-photo-id"]) {
        return current;
      }
      if (selector === ".result-card" && current._hasClass("result-card")) {
        return current;
      }
      if (selector === ".result-card-select" && current._hasClass("result-card-select")) {
        return current;
      }
      current = current.parentElement;
    }
    return null;
  }

  _hasClass(className) {
    return (this.attributes.class ?? "")
      .split(/\s+/)
      .filter(Boolean)
      .includes(className);
  }
}

class FakeDocument {
  constructor() {
    this.elements = new Map();
    this.listeners = {};
  }

  ensure(id) {
    if (!this.elements.has(id)) {
      this.elements.set(id, new FakeElement(id, this));
    }
    return this.elements.get(id);
  }

  getElementById(id) {
    return this.elements.get(id) ?? null;
  }

  addEventListener(type, callback) {
    if (!this.listeners[type]) {
      this.listeners[type] = [];
    }
    this.listeners[type].push(callback);
  }

  replaceInnerHTML(parent, value) {
    for (const child of parent.children) {
      this.unregisterTree(child);
    }
    parent.children = [];
    parent._innerHTML = value;

    if (parent.id === "results-region") {
      if (value.includes('class="empty-state"')) {
        const emptyState = new FakeElement(null, this);
        emptyState.setAttribute("class", "empty-state");
        parent.appendChild(emptyState);
        return;
      }

      const matches = value.matchAll(/<article\b[^>]*>[\s\S]*?<\/article>/g);
      for (const match of matches) {
        const articleMarkup = match[0];
        const articleTag = articleMarkup.match(/<article\b[^>]*>/)?.[0] ?? "";
        const buttonTag = articleMarkup.match(/<button\b[^>]*>/)?.[0] ?? "";
        if (!hasClassAttribute(articleTag, "result-card") || !hasClassAttribute(buttonTag, "result-card-select")) {
          continue;
        }

        const selected = readAttribute(articleTag, "data-selected") ?? "false";
        const photoId = readAttribute(buttonTag, "data-photo-id");
        const ariaPressed = readAttribute(buttonTag, "aria-pressed") ?? "false";
        if (!photoId) {
          continue;
        }

        const card = new FakeElement(null, this);
        card.setAttribute("class", "result-card");
        card.setAttribute("data-selected", selected);

        const button = new FakeElement(null, this);
        button.setAttribute("class", "result-card-select");
        button.setAttribute("data-photo-id", photoId);
        button.setAttribute("aria-pressed", ariaPressed);

        const nestedContent = new FakeElement(null, this);
        nestedContent.setAttribute("class", "result-card-image");
        button.appendChild(nestedContent);

        card.appendChild(button);

        parent.appendChild(card);
      }
      return;
    }

    const idMatches = value.matchAll(/id=(["'])([^"']+)\1/g);
    for (const match of idMatches) {
      parent.appendChild(this.ensure(match[2]));
    }
  }

  unregisterTree(element) {
    if (element.id) {
      this.elements.delete(element.id);
    }
    for (const child of element.children) {
      this.unregisterTree(child);
    }
  }
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function readAttribute(tagMarkup, attributeName) {
  const escapedName = attributeName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`${escapedName}=(["'])([^"']+)\\1`);
  return tagMarkup.match(pattern)?.[2] ?? null;
}

function hasClassAttribute(tagMarkup, className) {
  const classValue = readAttribute(tagMarkup, "class");
  if (!classValue) {
    return false;
  }
  return classValue.split(/\s+/).includes(className);
}

function createContext(fetchImpl) {
  const document = new FakeDocument();
  [
    "library-card",
    "models-card",
    "indexing-card",
    "device-card",
    "open-folder-action",
    "folder-list",
    "stage-title",
    "stage-subtitle",
    "stage-content",
    "detail-body",
  ].forEach((id) => document.ensure(id));

  const timers = [];
  let timerId = 0;

  const context = {
    console,
    document,
    fetch: fetchImpl,
    Element: FakeElement,
    setInterval(callback, delay) {
      const record = { id: ++timerId, callback, delay, cleared: false };
      timers.push(record);
      return record.id;
    },
    clearInterval(id) {
      const timer = timers.find((record) => record.id === id);
      if (timer) {
        timer.cleared = true;
      }
    },
    window: {},
  };
  context.window = context;
  vm.createContext(context);

  const appPath = path.join(__dirname, "..", "web", "app.js");
  const source = fs.readFileSync(appPath, "utf8");
  vm.runInContext(source, context);
  return {
    context,
    exports: {
      state: vm.runInContext("state", context),
      bootstrap: vm.runInContext("bootstrap", context),
      searchPhotos: vm.runInContext("searchPhotos", context),
      selectPhoto: vm.runInContext("selectPhoto", context),
      openFolderPicker: vm.runInContext("typeof openFolderPicker === 'function' ? openFolderPicker : null", context),
      startPollingIfNeeded: vm.runInContext("typeof startPollingIfNeeded === 'function' ? startPollingIfNeeded : null", context),
      stopPolling: vm.runInContext("typeof stopPolling === 'function' ? stopPolling : null", context),
    },
    document,
    timers,
  };
}

async function runBootstrapScenario() {
  const fetchImpl = async (requestPath) => {
    const payloads = {
      "/api/system/info": {
        version: "1.0.0",
        total_photos: 3,
        indexed_photos: 2,
      },
      "/api/library/folders": {
        folders: [{ id: 1, path: "/photos", photo_count: 3, indexed_count: 2 }],
      },
      "/api/index/status": { phase: "idle", processed: 0, total: 0 },
      "/api/models/download/status": { downloading: false, model: null, percent: 0 },
    };
    return {
      ok: true,
      async json() {
        return payloads[requestPath];
      },
    };
  };

  const { exports, document } = createContext(fetchImpl);
  await exports.bootstrap();

  assert(document.getElementById("folder-list").innerHTML.includes("/photos"), "bootstrap should render folders");
  assert(
    document.getElementById("stage-subtitle").textContent.includes("Library contains"),
    "bootstrap should update the stage subtitle",
  );
  assert(document.getElementById("search-form"), "bootstrap should mount the search scaffold");
  assert(
    document.getElementById("results-region").querySelectorAll("[data-photo-id]").length === 0,
    "bootstrap should start with no rendered search results",
  );
}

async function runFolderPathDisplayScenario() {
  const fullPath = "/Users/example/Pictures/Family/2026/April/Very Long Folder Name";
  const fetchImpl = async (requestPath) => {
    const payloads = {
      "/api/system/info": {
        version: "1.0.0",
        total_photos: 12,
        indexed_photos: 9,
      },
      "/api/library/folders": {
        folders: [{ id: 1, path: fullPath, photo_count: 12, indexed_count: 9 }],
      },
      "/api/index/status": { phase: "idle", processed: 0, total: 0 },
      "/api/models/download/status": { downloading: false, model: null, percent: 0 },
    };
    return {
      ok: true,
      async json() {
        return payloads[requestPath];
      },
    };
  };

  const { exports, document } = createContext(fetchImpl);
  await exports.bootstrap();

  const folderMarkup = document.getElementById("folder-list").innerHTML;
  assert(
    folderMarkup.includes("Pictures/Family/2026/April/Very Long Folder Name"),
    "folder card should show a home-relative path",
  );
  assert(!folderMarkup.includes("> /Users/example/"), "folder card should not show the full absolute path");
  assert(folderMarkup.includes(`title="${fullPath}"`), "folder card should expose the full path as a tooltip");
  assert(folderMarkup.includes("folder-progress-fill"), "folder card should render index progress");
}

async function runBootstrapFailureScenario() {
  const fetchImpl = async (requestPath) => {
    if (requestPath === "/api/system/info") {
      return { ok: true, async json() { return { version: "1.0.0", total_photos: 3, indexed_photos: 2 }; } };
    }
    if (requestPath === "/api/library/folders") {
      return {
        ok: true,
        async json() {
          return { folders: [{ id: 1, path: "/photos", photo_count: 3, indexed_count: 2 }] };
        },
      };
    }
    if (requestPath === "/api/index/status") {
      return { ok: true, async json() { return { phase: "idle", processed: 0, total: 0 }; } };
    }
    if (requestPath === "/api/models/download/status") {
      throw new Error("download probe failed");
    }
    throw new Error(`Unexpected request: ${requestPath}`);
  };

  const { exports, document } = createContext(fetchImpl);
  await exports.bootstrap();

  assert(
    document.getElementById("stage-title").textContent === "Gallery unavailable",
    "bootstrap failure should switch the stage title to a fatal state",
  );
  assert(
    document.getElementById("stage-content").innerHTML.includes("download probe failed"),
    "bootstrap failure should render the fatal error message",
  );
}

async function runBootstrapPollingScenario() {
  const fetchImpl = async (requestPath) => {
    const payloads = {
      "/api/system/info": {
        version: "1.0.0",
        total_photos: 3,
        indexed_photos: 2,
      },
      "/api/library/folders": {
        folders: [{ id: 1, path: "/photos", photo_count: 3, indexed_count: 2 }],
      },
      "/api/index/status": {
        is_running: true,
        phase: "indexing",
        processed: 4,
        total: 10,
        failed: 0,
        current_file: "one.jpg",
        progress_percent: 40,
        eta_seconds: 12,
        speed_per_second: 1.2,
      },
      "/api/models/download/status": {
        downloading: true,
        model: "clip_visual",
        percent: 25,
        error: null,
      },
    };
    return {
      ok: true,
      async json() {
        return payloads[requestPath];
      },
    };
  };

  const { exports, timers } = createContext(fetchImpl);
  await exports.bootstrap();

  assert(typeof exports.startPollingIfNeeded === "function", "bootstrap should expose startPollingIfNeeded");
  assert(timers.length === 2, "bootstrap should start polling for active indexing and downloads");
  assert(timers.some((timer) => timer.delay === 2000), "bootstrap should start the index polling interval");
  assert(timers.some((timer) => timer.delay === 1500), "bootstrap should start the download polling interval");
  exports.startPollingIfNeeded();
  assert(timers.length === 2, "starting polling again should not register duplicate intervals");
  exports.stopPolling();
  assert(timers.every((timer) => timer.cleared), "stopPolling should clear the active polling intervals");
}

async function runSearchSubmitScenario() {
  const fetchImpl = async (requestPath) => {
    if (requestPath === "/api/system/info") {
      return { ok: true, async json() { return { total_photos: 3, indexed_photos: 2 }; } };
    }
    if (requestPath === "/api/library/folders") {
      return {
        ok: true,
        async json() {
          return { folders: [{ id: 1, path: "/photos", photo_count: 3, indexed_count: 2 }] };
        },
      };
    }
    if (requestPath === "/api/index/status") {
      return { ok: true, async json() { return { phase: "idle", processed: 0, total: 0 }; } };
    }
    if (requestPath === "/api/models/download/status") {
      return { ok: true, async json() { return { downloading: false, model: null, percent: 0 }; } };
    }
    if (requestPath === "/api/search?q=%E6%A3%AE%E6%9E%97") {
      return {
        ok: true,
        async json() {
          return {
            results: [
              {
                id: 1,
                filename: "forest.jpg",
                thumbnail_url: "/api/thumbnail/1",
                full_image_url: "/api/image/1",
                similarity: 0.84,
                match_score: 96,
                taken_at: "2024-03-14T10:00:00+00:00",
              },
              {
                id: 2,
                filename: "trees.jpg",
                thumbnail_url: "/api/thumbnail/2",
                full_image_url: "/api/image/2",
                similarity: 0.62,
                match_score: 42,
                taken_at: "2024-03-15T11:00:00+00:00",
              },
            ],
            rewritten_query: "forest",
          };
        },
      };
    }
    throw new Error(`Unexpected request: ${requestPath}`);
  };

  const { exports, document } = createContext(fetchImpl);
  await exports.bootstrap();

  const searchInput = document.getElementById("search-input");
  const searchForm = document.getElementById("search-form");
  searchInput.value = "森林";
  await searchForm.dispatchEvent({
    type: "submit",
    preventDefault() {},
  });

  const resultsRegion = document.getElementById("results-region");
  const renderedCards = resultsRegion.querySelectorAll("[data-photo-id]");
  assert(renderedCards.length === 2, "search submit should render the returned results");
  assert(
    document.getElementById("search-feedback").textContent.includes("Chinese query rewritten as: forest"),
    "search submit should render the rewritten query feedback",
  );
  assert(
    document.getElementById("detail-body").innerHTML.includes("forest.jpg"),
    "search submit should select the first result in the detail panel",
  );
  assert(
    document.getElementById("detail-body").innerHTML.includes('/api/image/1'),
    "detail panel should expose a direct original image link",
  );
  assert(resultsRegion.innerHTML.includes("Match 96"), "best result should render the backend match score");
  assert(resultsRegion.innerHTML.includes("Match 42"), "weaker result should render the backend match score");
  assert(!resultsRegion.innerHTML.includes("Similarity 0.84"), "result cards should not expose raw similarity decimals");

  await resultsRegion.dispatchEvent({
    type: "click",
    target: renderedCards[1].children[0],
  });
  assert(renderedCards[0].getAttribute("aria-pressed") === "false", "delegated click should deselect the old result");
  assert(renderedCards[1].getAttribute("aria-pressed") === "true", "delegated click should select the clicked result");
  assert(
    document.getElementById("detail-body").innerHTML.includes("trees.jpg"),
    "delegated click should update the detail panel",
  );
  assert(
    document.getElementById("detail-body").innerHTML.includes('/api/image/2'),
    "detail panel should keep the selected image link in sync",
  );
  assert(document.getElementById("detail-body").innerHTML.includes("Match 42"), "detail panel should show backend match score");
}

async function runNoSearchMatchesScenario() {
  const fetchImpl = async (requestPath) => {
    if (requestPath === "/api/system/info") {
      return { ok: true, async json() { return { total_photos: 3, indexed_photos: 2 }; } };
    }
    if (requestPath === "/api/library/folders") {
      return {
        ok: true,
        async json() {
          return { folders: [{ id: 1, path: "/photos", photo_count: 3, indexed_count: 2 }] };
        },
      };
    }
    if (requestPath === "/api/index/status") {
      return { ok: true, async json() { return { phase: "idle", processed: 0, total: 0 }; } };
    }
    if (requestPath === "/api/models/download/status") {
      return { ok: true, async json() { return { downloading: false, model: null, percent: 0 }; } };
    }
    if (requestPath === "/api/search?q=nomatch") {
      return {
        ok: true,
        async json() {
          return {
            results: [],
            rewritten_query: null,
          };
        },
      };
    }
    throw new Error(`Unexpected request: ${requestPath}`);
  };

  const { exports, document } = createContext(fetchImpl);
  await exports.bootstrap();

  const searchInput = document.getElementById("search-input");
  const searchForm = document.getElementById("search-form");
  searchInput.value = "nomatch";
  await searchForm.dispatchEvent({ type: "submit", preventDefault() {} });

  assert(
    document.getElementById("results-region").innerHTML.includes("No matches found"),
    "empty result searches should render a no-matches state",
  );
}

async function runStaleSearchScenario() {
  const first = deferred();
  const second = deferred();
  let searchCount = 0;

  const fetchImpl = async (requestPath) => {
    if (requestPath === "/api/system/info") {
      return { ok: true, async json() { return { total_photos: 3, indexed_photos: 2 }; } };
    }
    if (requestPath === "/api/library/folders") {
      return {
        ok: true,
        async json() {
          return { folders: [{ id: 1, path: "/photos", photo_count: 3, indexed_count: 2 }] };
        },
      };
    }
    if (requestPath === "/api/index/status") {
      return { ok: true, async json() { return { phase: "idle", processed: 0, total: 0 }; } };
    }
    if (requestPath === "/api/models/download/status") {
      return { ok: true, async json() { return { downloading: false, model: null, percent: 0 }; } };
    }
    if (requestPath.startsWith("/api/search?q=")) {
      searchCount += 1;
      const current = searchCount === 1 ? first : second;
      return {
        ok: true,
        async json() {
          return current.promise;
        },
      };
    }
    throw new Error(`Unexpected request: ${requestPath}`);
  };

  const { exports, document } = createContext(fetchImpl);
  await exports.bootstrap();

  const searchInput = document.getElementById("search-input");
  const searchForm = document.getElementById("search-form");
  searchInput.value = "forest";
  const firstSubmit = searchForm.dispatchEvent({ type: "submit", preventDefault() {} });
  searchInput.value = "sunset";
  const secondSubmit = searchForm.dispatchEvent({ type: "submit", preventDefault() {} });

  second.resolve({
    results: [{ id: 2, filename: "sunset.jpg", thumbnail_url: "/api/thumbnail/2", full_image_url: "/api/image/2", similarity: 0.9, match_score: 98 }],
    rewritten_query: null,
  });
  await secondSubmit;

  first.resolve({
    results: [{ id: 1, filename: "forest.jpg", thumbnail_url: "/api/thumbnail/1", full_image_url: "/api/image/1", similarity: 0.8, match_score: 91 }],
    rewritten_query: null,
  });
  await firstSubmit;

  const renderedCards = document.getElementById("results-region").querySelectorAll("[data-photo-id]");
  assert(renderedCards.length === 1, "stale search should leave only the latest rendered result");
  assert(
    renderedCards[0].getAttribute("data-photo-id") === "2",
    "stale search should keep the latest result mounted in the DOM",
  );
  assert(
    document.getElementById("detail-body").innerHTML.includes("sunset.jpg"),
    "stale search should keep the latest detail preview rendered",
  );
}

async function runOpenFolderScenario() {
  const requests = [];
  let folderPhase = 0;

  const fetchImpl = async (requestPath, options = {}) => {
    requests.push({ path: requestPath, method: options.method ?? "GET", body: options.body ?? null });

    if (requestPath === "/api/system/info") {
      return {
        ok: true,
        async json() {
          if (folderPhase === 0) {
            return { total_photos: 0, indexed_photos: 0 };
          }
          return { total_photos: 6, indexed_photos: 0 };
        },
      };
    }
    if (requestPath === "/api/library/folders") {
      return {
        ok: true,
        async json() {
          if (folderPhase === 0) {
            return { folders: [] };
          }
          return {
            folders: [{ id: 2, path: "/imports/new", photo_count: 0, indexed_count: 0 }],
          };
        },
      };
    }
    if (requestPath === "/api/index/status") {
      return {
        ok: true,
        async json() {
          if (folderPhase === 0) {
            return {
              is_running: false,
              phase: "idle",
              processed: 0,
              total: 0,
              failed: 0,
              current_file: "",
              progress_percent: 0,
              eta_seconds: 0,
              speed_per_second: 0,
            };
          }
          return {
            is_running: true,
            phase: "indexing",
            processed: 0,
            total: 12,
            failed: 0,
            current_file: "new.jpg",
            progress_percent: 0,
            eta_seconds: 90,
            speed_per_second: 0.3,
          };
        },
      };
    }
    if (requestPath === "/api/models/download/status") {
      return {
        ok: true,
        async json() {
          return { downloading: false, model: null, percent: 0, error: null };
        },
      };
    }
    if (requestPath === "/api/system/open-folder") {
      return {
        ok: true,
        async json() {
          return { selected_path: "/imports/new" };
        },
      };
    }
    if (requestPath === "/api/library/add") {
      folderPhase = 1;
      return {
        ok: true,
        async json() {
          return { folder_id: 2, path: "/imports/new", status: "scanning_started" };
        },
      };
    }
    throw new Error(`Unexpected request: ${requestPath}`);
  };

  const { exports, document, timers } = createContext(fetchImpl);
  await exports.bootstrap();

  const openFolderAction = document.getElementById("open-folder-action");
  assert(openFolderAction, "open-folder action should exist in the drawer");
  await openFolderAction.dispatchEvent({ type: "click", preventDefault() {} });

  assert(
    requests.some((request) => request.path === "/api/library/add" && request.method === "POST"),
    "open-folder click should post the selected folder to the library API",
  );
  assert(
    document.getElementById("folder-list").innerHTML.includes("/imports/new"),
    "open-folder click should refresh the drawer folder list",
  );
  assert(
    timers.some((timer) => timer.delay === 2000),
    "open-folder click should start index polling when the refreshed status is running",
  );
  assert(
    document.getElementById("stage-title").textContent === "Gallery",
    "open-folder click should refresh the center stage after library data changes",
  );
}

async function runOpenFolderFailureScenario() {
  const fetchImpl = async (requestPath) => {
    if (requestPath === "/api/system/info") {
      return { ok: true, async json() { return { total_photos: 0, indexed_photos: 0 }; } };
    }
    if (requestPath === "/api/library/folders") {
      return { ok: true, async json() { return { folders: [] }; } };
    }
    if (requestPath === "/api/index/status") {
      return {
        ok: true,
        async json() {
          return {
            is_running: false,
            phase: "idle",
            processed: 0,
            total: 0,
            failed: 0,
            current_file: "",
            progress_percent: 0,
            eta_seconds: 0,
            speed_per_second: 0,
          };
        },
      };
    }
    if (requestPath === "/api/models/download/status") {
      return { ok: true, async json() { return { downloading: false, model: null, percent: 0, error: null }; } };
    }
    if (requestPath === "/api/system/open-folder") {
      throw new Error("picker failed");
    }
    throw new Error(`Unexpected request: ${requestPath}`);
  };

  const { exports, document } = createContext(fetchImpl);
  await exports.bootstrap();

  const openFolderAction = document.getElementById("open-folder-action");
  await openFolderAction.dispatchEvent({ type: "click", preventDefault() {} });

  assert(
    document.getElementById("folder-list").innerHTML.includes("picker failed"),
    "open-folder failure should stay local to the drawer",
  );
  assert(
    document.getElementById("stage-title").textContent !== "Gallery unavailable",
    "open-folder failure should not replace the main stage with a fatal bootstrap error",
  );
}

async function runPollingGuardScenario() {
  const pendingPoll = deferred();
  let indexStatusRequests = 0;

  const fetchImpl = async (requestPath) => {
    if (requestPath === "/api/system/info") {
      return { ok: true, async json() { return { total_photos: 3, indexed_photos: 2 }; } };
    }
    if (requestPath === "/api/library/folders") {
      return {
        ok: true,
        async json() {
          return { folders: [{ id: 1, path: "/photos", photo_count: 3, indexed_count: 2 }] };
        },
      };
    }
    if (requestPath === "/api/index/status") {
      indexStatusRequests += 1;
      if (indexStatusRequests === 1) {
        return {
          ok: true,
          async json() {
            return {
              is_running: true,
              phase: "indexing",
              processed: 2,
              total: 10,
              failed: 0,
              current_file: "one.jpg",
              progress_percent: 20,
              eta_seconds: 20,
              speed_per_second: 1.0,
            };
          },
        };
      }
      return {
        ok: true,
        async json() {
          return pendingPoll.promise;
        },
      };
    }
    if (requestPath === "/api/models/download/status") {
      return {
        ok: true,
        async json() {
          return { downloading: false, model: null, percent: 0, error: null };
        },
      };
    }
    throw new Error(`Unexpected request: ${requestPath}`);
  };

  const { exports, timers } = createContext(fetchImpl);
  await exports.bootstrap();

  const indexTimer = timers.find((timer) => timer.delay === 2000);
  assert(indexTimer, "bootstrap should register the index polling timer");

  indexTimer.callback();
  indexTimer.callback();
  assert(indexStatusRequests === 2, "overlapping index poll ticks should collapse to a single in-flight request");

  pendingPoll.resolve({
    is_running: true,
    phase: "indexing",
    processed: 3,
    total: 10,
    failed: 0,
    current_file: "two.jpg",
    progress_percent: 30,
    eta_seconds: 18,
    speed_per_second: 1.0,
  });
  await Promise.resolve();
}

async function runPollingErrorScenario() {
  let indexStatusRequests = 0;

  const fetchImpl = async (requestPath) => {
    if (requestPath === "/api/system/info") {
      return { ok: true, async json() { return { total_photos: 3, indexed_photos: 2 }; } };
    }
    if (requestPath === "/api/library/folders") {
      return {
        ok: true,
        async json() {
          return { folders: [{ id: 1, path: "/photos", photo_count: 3, indexed_count: 2 }] };
        },
      };
    }
    if (requestPath === "/api/index/status") {
      indexStatusRequests += 1;
      if (indexStatusRequests === 1) {
        return {
          ok: true,
          async json() {
            return {
              is_running: true,
              phase: "indexing",
              processed: 2,
              total: 10,
              failed: 0,
              current_file: "one.jpg",
              progress_percent: 20,
              eta_seconds: 20,
              speed_per_second: 1.0,
            };
          },
        };
      }
      throw new Error("index status failed");
    }
    if (requestPath === "/api/models/download/status") {
      return {
        ok: true,
        async json() {
          return { downloading: false, model: null, percent: 0, error: null };
        },
      };
    }
    throw new Error(`Unexpected request: ${requestPath}`);
  };

  const { exports, document, timers } = createContext(fetchImpl);
  await exports.bootstrap();

  const indexTimer = timers.find((timer) => timer.delay === 2000);
  assert(indexTimer, "bootstrap should register the index polling timer");

  await indexTimer.callback();
  assert(indexTimer.cleared === true, "failing index polling should clear the timer");
  assert(
    document.getElementById("detail-body").innerHTML.includes("index status failed"),
    "failing index polling should surface the polling error in the detail panel",
  );
}

async function main() {
  const scenario = process.argv[2];
  if (scenario === "bootstrap") {
    await runBootstrapScenario();
    return;
  }
  if (scenario === "folder-path-display") {
    await runFolderPathDisplayScenario();
    return;
  }
  if (scenario === "bootstrap-failure") {
    await runBootstrapFailureScenario();
    return;
  }
  if (scenario === "bootstrap-polling") {
    await runBootstrapPollingScenario();
    return;
  }
  if (scenario === "open-folder") {
    await runOpenFolderScenario();
    return;
  }
  if (scenario === "open-folder-failure") {
    await runOpenFolderFailureScenario();
    return;
  }
  if (scenario === "polling-guard") {
    await runPollingGuardScenario();
    return;
  }
  if (scenario === "polling-error") {
    await runPollingErrorScenario();
    return;
  }
  if (scenario === "search-submit") {
    await runSearchSubmitScenario();
    return;
  }
  if (scenario === "no-search-matches") {
    await runNoSearchMatchesScenario();
    return;
  }
  if (scenario === "stale-search") {
    await runStaleSearchScenario();
    return;
  }
  throw new Error(`Unknown scenario: ${scenario}`);
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
