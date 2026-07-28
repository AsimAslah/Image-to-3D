(() => {
  const form = document.getElementById("conversion-form");
  const imageInput = document.getElementById("image-input");
  const qualityMode = document.getElementById("quality-mode");
  const convertButton = document.getElementById("convert-button");
  const saveButton = document.getElementById("save-button");
  const progressPanel = document.getElementById("conversion-progress");
  const progressBar = document.getElementById("progress-bar");
  const progressStatus = document.getElementById("progress-status");
  const progressPercent = document.getElementById("progress-percent");
  const progressElapsed = document.getElementById("progress-elapsed");
  const conversionResult = document.getElementById("conversion-result");
  const toastArea = document.getElementById("toast-area");
  const deviceSupport = document.getElementById("device-support");
  const modelLibrary = document.getElementById("model-library");
  const modelLibraryGrid = document.getElementById("model-library-grid");
  const modelLibrarySkeletons = document.getElementById("model-library-skeletons");
  const modelLibraryStatus = document.getElementById("model-library-status");
  const modelLibraryCount = document.getElementById("model-library-count");
  const modelLibraryEmpty = document.getElementById("model-library-empty");
  const modelLibraryNoResults = document.getElementById("model-library-no-results");
  const modelLibraryError = document.getElementById("model-library-error");
  const modelLibrarySearch = document.getElementById("model-library-search");
  const modelLibraryCategory = document.getElementById("model-library-category");
  const modelLibraryCategoryWrap = document.getElementById("model-library-category-wrap");
  const modelCardTemplate = document.getElementById("model-card-template");
  const activePreviews = new Map();
  let savedModels = [];
  let modelLibraryPromise;
  let modelViewerPromise;
  let conversionStartedAt = 0;
  let conversionElapsedTimer;
  let conversionPollController;

  const MB = 1024 * 1024;
  const PREVIEW_TIMEOUT_MS = 120000;

  function isIOS() {
    const ua = navigator.userAgent || "";
    return /iPad|iPhone|iPod/.test(ua)
      || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function isAndroid() {
    return /Android/i.test(navigator.userAgent || "");
  }

  function isMobile() {
    return isIOS() || isAndroid() || window.matchMedia("(max-width: 767px) and (pointer: coarse)").matches;
  }

  function isStandalone() {
    return window.matchMedia("(display-mode: standalone)").matches
      || window.navigator.standalone === true;
  }

  function platformName() {
    if (isIOS()) return "ios";
    if (isAndroid()) return "android";
    return "desktop";
  }

  function formatBytes(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} bytes`;
    if (value < MB) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / MB).toFixed(1)} MB`;
  }

  function notify(message, type = "info") {
    if (!toastArea || !message) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toastArea.appendChild(toast);
    window.setTimeout(() => toast.remove(), 5200);
  }

  function setConversionProgress(status, percent = null) {
    progressStatus.textContent = status;
    if (Number.isFinite(percent)) {
      const measured = Math.max(0, Math.min(100, Math.round(percent)));
      progressBar.value = measured;
      progressBar.textContent = `${measured}%`;
      progressPercent.hidden = false;
      progressPercent.textContent = `${measured}%`;
    } else {
      progressBar.removeAttribute("value");
      progressBar.textContent = status;
      progressPercent.hidden = false;
      progressPercent.textContent = "—";
    }
  }

  function updateConversionElapsed() {
    if (!progressElapsed || !conversionStartedAt) return;
    const elapsed = Math.max(0, Math.floor((Date.now() - conversionStartedAt) / 1000));
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    progressElapsed.textContent = minutes
      ? `Elapsed ${minutes}m ${String(seconds).padStart(2, "0")}s`
      : `Elapsed ${seconds}s`;
  }

  function startConversionTimer() {
    conversionStartedAt = Date.now();
    window.clearInterval(conversionElapsedTimer);
    updateConversionElapsed();
    conversionElapsedTimer = window.setInterval(updateConversionElapsed, 1000);
  }

  function stopConversionTimer() {
    window.clearInterval(conversionElapsedTimer);
    conversionElapsedTimer = null;
    updateConversionElapsed();
  }

  function setProductSaveAvailability(locked) {
    const dimensionsReady = document.querySelector("[data-preview-root]")?.dataset.dimensionsReady === "true";
    document.querySelectorAll('[form="product-form"]').forEach((button) => {
      button.disabled = locked || !dimensionsReady;
    });
  }

  function setConversionLocked(locked) {
    imageInput.disabled = locked;
    convertButton.disabled = locked;
    document.querySelectorAll("#product-form input, #product-form textarea, #product-form select").forEach((field) => {
      field.disabled = locked;
    });
    setProductSaveAvailability(locked);
  }

  function updateDeviceSummary() {
    const standalone = isStandalone() ? "installed PWA" : "browser";
    if (isIOS()) {
      deviceSupport.textContent = `iPhone/iPad ${standalone} • Apple Quick Look uses validated USDZ`;
    } else if (isAndroid()) {
      deviceSupport.textContent = `Android ${standalone} • Scene Viewer uses validated GLB`;
    } else {
      deviceSupport.textContent = "Desktop 3D preview • use a supported phone for AR";
    }
    console.info("[Furniture AR] device", {
      platform: platformName(), standalone: isStandalone(), secureContext: window.isSecureContext,
    });
  }

  function hasWebGL() {
    try {
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("webgl2") || canvas.getContext("webgl");
      context?.getExtension("WEBGL_lose_context")?.loseContext();
      return Boolean(context);
    } catch (_error) {
      return false;
    }
  }

  function previewElements(root) {
    return {
      card: root.querySelector("[data-preview-card]"),
      heading: root.querySelector("[data-preview-heading]"),
      status: root.querySelector("[data-preview-status]"),
      message: root.querySelector("[data-preview-message]"),
      progressWrap: root.querySelector("[data-preview-progress]"),
      progress: root.querySelector("[data-preview-progress] progress"),
      surface: root.querySelector("[data-preview-surface]"),
      error: root.querySelector("[data-preview-error]"),
      errorMessage: root.querySelector("[data-preview-error-message]"),
      errorDownload: root.querySelector(".preview-error-download"),
      retry: root.querySelector(".retry-preview"),
      type: root.querySelector("[data-diagnostic-type]"),
      size: root.querySelector("[data-diagnostic-size]"),
      stage: root.querySelector("[data-diagnostic-stage]"),
      http: root.querySelector("[data-diagnostic-http]"),
      detail: root.querySelector("[data-diagnostic-detail]"),
    };
  }

  function setPreviewStage(root, stage, message, options = {}) {
    const elements = previewElements(root);
    if (stage !== "ready") elements.status.classList.remove("is-ready");
    elements.stage.textContent = stage;
    elements.message.textContent = message;
    elements.status.hidden = false;
    elements.error.hidden = true;
    if (options.loaded != null) {
      const total = options.total || 0;
      elements.progressWrap.hidden = false;
      if (total > 0) {
        elements.progress.value = Math.min(100, (options.loaded / total) * 100);
        elements.progress.textContent = `${Math.round((options.loaded / total) * 100)}%`;
      } else {
        elements.progress.removeAttribute("value");
      }
    } else {
      elements.progressWrap.hidden = true;
    }
  }

  function setTriggersBusy(root, busy) {
    root.querySelectorAll(".preview-trigger").forEach((button) => {
      button.disabled = busy || button.dataset.previewUnavailable === "true";
      button.setAttribute("aria-busy", String(busy));
    });
  }

  async function fetchModel(url, declaredSize, signal, onProgress) {
    const response = await fetch(url, { cache: "no-store", credentials: "same-origin", signal });
    if (!response.ok) {
      const error = new Error(`The server returned HTTP ${response.status}.`);
      error.stage = "download";
      error.httpStatus = response.status;
      throw error;
    }
    const headerSize = Number(response.headers.get("content-length")) || 0;
    const total = headerSize || declaredSize || 0;
    if (!response.body?.getReader) {
      const blob = await response.blob();
      onProgress(blob.size, total || blob.size);
      return { blob, httpStatus: response.status };
    }
    const reader = response.body.getReader();
    const chunks = [];
    let loaded = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      loaded += value.byteLength;
      onProgress(loaded, total);
    }
    const contentType = response.headers.get("content-type") || "application/octet-stream";
    return { blob: new Blob(chunks, { type: contentType }), httpStatus: response.status };
  }

  function unloadPreview(root, { hide = true } = {}) {
    const active = activePreviews.get(root);
    if (active) {
      active.controller?.abort();
      try { active.cleanup?.(); } catch (error) { console.warn("[Preview] cleanup failed", error); }
      if (active.objectUrl) URL.revokeObjectURL(active.objectUrl);
      activePreviews.delete(root);
    }
    const elements = previewElements(root);
    elements.surface.replaceChildren();
    elements.surface.hidden = true;
    elements.status.classList.remove("is-ready");
    elements.status.hidden = false;
    elements.error.hidden = true;
    elements.progressWrap.hidden = true;
    if (hide) elements.card.hidden = true;
    setTriggersBusy(root, false);
  }

  function sizeAllowsPreview(type, size) {
    if (!isMobile() || size < 10 * MB) return true;
    if (size > 25 * MB) {
      return window.confirm(
        `The ${type.toUpperCase()} file is ${formatBytes(size)}. Loading it may use significant mobile data and memory. Load it now?`,
      );
    }
    notify(`${type.toUpperCase()} is ${formatBytes(size)}; mobile loading may take longer.`, "info");
    return true;
  }

  async function ensureModelViewer() {
    if (!modelViewerPromise) {
      modelViewerPromise = import("https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js")
        .then(() => customElements.whenDefined("model-viewer"));
    }
    return modelViewerPromise;
  }

  async function mountGlb(root, objectUrl, active) {
    if (!hasWebGL()) {
      const error = new Error("WebGL is unavailable or disabled in this browser.");
      error.stage = "rendering";
      throw error;
    }
    setPreviewStage(root, "rendering", "Loading 3D viewer...");
    await ensureModelViewer();
    if (active.controller.signal.aborted) throw new DOMException("Aborted", "AbortError");
    const elements = previewElements(root);
    const viewer = document.createElement("model-viewer");
    viewer.className = "lazy-model-viewer";
    viewer.setAttribute("alt", "Generated furniture 3D model");
    viewer.setAttribute("camera-controls", "");
    viewer.setAttribute("auto-rotate", "");
    viewer.setAttribute("shadow-intensity", "1");
    viewer.setAttribute("exposure", "1.05");
    viewer.setAttribute("field-of-view", "35deg");
    elements.surface.replaceChildren(viewer);
    elements.surface.hidden = false;
    active.cleanup = () => {
      viewer.pause?.();
      viewer.removeAttribute("src");
      viewer.remove();
    };
    await new Promise((resolve, reject) => {
      let settled = false;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeout);
        active.controller.signal.removeEventListener("abort", onAbort);
        callback(value);
      };
      const timeout = window.setTimeout(() => {
        const error = new Error("The viewer did not finish parsing the GLB within 45 seconds.");
        error.stage = "parsing";
        finish(reject, error);
      }, 45000);
      const onAbort = () => finish(reject, new DOMException("Preview loading was cancelled.", "AbortError"));
      active.controller.signal.addEventListener("abort", onAbort, { once: true });
      viewer.addEventListener("load", () => {
        setPreviewStage(root, "materials", "Applying materials...");
        requestAnimationFrame(() => finish(resolve));
      }, { once: true });
      viewer.addEventListener("error", (event) => {
        const error = new Error(event.detail?.message || "model-viewer could not parse or render this GLB.");
        error.stage = "parsing/rendering";
        finish(reject, error);
      }, { once: true });
      if (active.controller.signal.aborted) {
        onAbort();
        return;
      }
      viewer.src = objectUrl;
    });
  }

  async function mountObj(root, blob, active) {
    if (!hasWebGL()) {
      const error = new Error("WebGL is unavailable or disabled in this browser.");
      error.stage = "rendering";
      throw error;
    }
    setPreviewStage(root, "geometry", "Loading geometry...");
    const module = await import(`/static/obj-preview.js?v=${encodeURIComponent(window.APP_VERSION || "current")}`);
    if (active.controller.signal.aborted) throw new DOMException("Aborted", "AbortError");
    const elements = previewElements(root);
    elements.surface.hidden = false;
    const controller = await module.createObjPreview(elements.surface, await blob.text(), (stage) => {
      if (stage === "materials") setPreviewStage(root, "materials", "Applying materials...");
    });
    active.cleanup = () => controller.dispose();
  }

  function showPreviewError(root, type, size, downloadUrl, error) {
    const elements = previewElements(root);
    const stage = error.stage || (error.name === "AbortError" ? "cancelled" : "unknown");
    const status = error.httpStatus || "No response";
    const userMessage = error.name === "AbortError"
      ? "Preview loading was cancelled or timed out. You can retry without converting again."
      : `${type.toUpperCase()} preview failed during ${stage}. You can retry or open the model file directly.`;
    elements.status.hidden = true;
    elements.progressWrap.hidden = true;
    elements.surface.hidden = true;
    elements.error.hidden = false;
    elements.errorMessage.textContent = userMessage;
    elements.errorDownload.href = downloadUrl;
    elements.type.textContent = type.toUpperCase();
    elements.size.textContent = formatBytes(size);
    elements.stage.textContent = stage;
    elements.http.textContent = String(status);
    elements.detail.textContent = error.message || error.name || "Unknown preview error";
    console.error("[Preview] load failed", { type, size, stage, httpStatus: status, error });
    notify(`${type.toUpperCase()} preview could not be loaded.`, "error");
  }

  async function loadPreview(root, config) {
    const { type, url, downloadUrl, size, label } = config;
    const existing = activePreviews.get(root);
    if (existing?.type === type && existing?.url === url) {
      const elements = previewElements(root);
      if (label) elements.heading.textContent = `${label} — 3D Preview`;
      elements.card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
    if (!sizeAllowsPreview(type, size)) return;
    [...activePreviews.keys()].forEach((previewRoot) => {
      if (previewRoot !== root) unloadPreview(previewRoot);
    });
    if (existing) unloadPreview(root, { hide: false });
    unloadPreview(root, { hide: false });
    const elements = previewElements(root);
    elements.card.hidden = false;
    elements.heading.textContent = label ? `${label} — 3D Preview` : `${type.toUpperCase()} Preview`;
    elements.type.textContent = type.toUpperCase();
    elements.size.textContent = formatBytes(size);
    elements.stage.textContent = "preparing";
    elements.http.textContent = "Pending";
    elements.detail.textContent = "None";
    elements.errorDownload.href = downloadUrl;
    elements.retry.dataset.previewType = type;
    elements.retry.dataset.previewUrl = url;
    elements.retry.dataset.downloadUrl = downloadUrl;
    elements.retry.dataset.fileSize = String(size);
    elements.retry.dataset.previewLabel = label || "";
    elements.card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setTriggersBusy(root, true);
    setPreviewStage(root, "preparing", "Preparing preview...");

    const controller = new AbortController();
    const active = { ...config, controller, cleanup: null, objectUrl: null };
    activePreviews.set(root, active);
    const timeout = window.setTimeout(() => controller.abort(), PREVIEW_TIMEOUT_MS);
    try {
      const response = await fetchModel(url, size, controller.signal, (loaded, total) => {
        const copy = total ? `${formatBytes(loaded)} of ${formatBytes(total)}` : formatBytes(loaded);
        setPreviewStage(root, "download", `Downloading model: ${copy}`, { loaded, total });
      });
      elements.http.textContent = String(response.httpStatus);
      active.objectUrl = URL.createObjectURL(response.blob);
      if (type === "glb") await mountGlb(root, active.objectUrl, active);
      else await mountObj(root, response.blob, active);
      setPreviewStage(root, "ready", "Ready — drag to rotate, pinch or scroll to zoom.");
      elements.status.classList.add("is-ready");
      setTriggersBusy(root, false);
      console.info("[Preview] ready", { type, size, httpStatus: response.httpStatus });
    } catch (error) {
      if (activePreviews.get(root) !== active) return;
      active.cleanup?.();
      if (active.objectUrl) URL.revokeObjectURL(active.objectUrl);
      active.cleanup = null;
      active.objectUrl = null;
      activePreviews.delete(root);
      showPreviewError(root, type, size, downloadUrl, error);
      setTriggersBusy(root, false);
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function secureExperienceAvailable() {
    return window.isSecureContext
      || location.hostname === "localhost"
      || location.hostname === "127.0.0.1";
  }

  function safeLibraryUrl(value, suffix = null) {
    if (typeof value !== "string" || !value.trim()) return null;
    try {
      const url = new URL(value);
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
      if (suffix && !decodeURIComponent(url.pathname).toLowerCase().endsWith(suffix)) return null;
      return url.href;
    } catch (_error) {
      return null;
    }
  }

  function isSecureAssetUrl(value) {
    try {
      return new URL(value).protocol === "https:";
    } catch (_error) {
      return false;
    }
  }

  function launchAndroidAR(modelUrl) {
    const file = encodeURIComponent(new URL(modelUrl).href);
    const fallback = encodeURIComponent(location.href);
    location.href = `intent://arvr.google.com/scene-viewer/1.0?file=${file}&mode=ar_preferred#Intent;scheme=https;package=com.google.ar.core;action=android.intent.action.VIEW;S.browser_fallback_url=${fallback};end;`;
    sessionStorage.setItem("furniture-ar-launched", "true");
  }

  function normalizeSavedModel(value, index) {
    if (!value || typeof value !== "object") return null;
    const dimensionValues = value.dimensions && typeof value.dimensions === "object"
      ? ["width", "height", "depth"].map((field) => Number(value.dimensions[field]))
      : [];
    const dimensions = dimensionValues.length === 3
      && dimensionValues.every((number) => Number.isFinite(number) && number > 0)
      ? {
        width: dimensionValues[0],
        height: dimensionValues[1],
        depth: dimensionValues[2],
        unit: String(value.dimensions.unit || "m").slice(0, 12),
      }
      : null;
    const price = value.price == null ? null : Number(value.price);
    return {
      key: String(index),
      id: typeof value.id === "string" ? value.id.slice(0, 128) : null,
      name: typeof value.name === "string" && value.name.trim()
        ? value.name.trim().slice(0, 160)
        : "Untitled model",
      category: typeof value.category === "string" && value.category.trim()
        ? value.category.trim().slice(0, 100)
        : null,
      description: typeof value.description === "string" && value.description.trim()
        ? value.description.trim().slice(0, 2000)
        : null,
      price: Number.isFinite(price) && price >= 0 ? price : null,
      dimensions,
      createdAt: typeof value.created_at === "string" && !Number.isNaN(Date.parse(value.created_at))
        ? value.created_at
        : null,
      thumbnailUrl: safeLibraryUrl(value.thumbnail_url),
      glbUrl: safeLibraryUrl(value.glb_url, ".glb"),
      usdzUrl: safeLibraryUrl(value.usdz_url, ".usdz"),
      objUrl: safeLibraryUrl(value.obj_url, ".obj"),
    };
  }

  function formattedPrice(price) {
    return `Price ${new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(price)}`;
  }

  function formattedDimensions(dimensions) {
    const format = new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 });
    return `${format.format(dimensions.width)} × ${format.format(dimensions.height)} × ${format.format(dimensions.depth)} ${dimensions.unit}`;
  }

  function setModelCardStatus(card, message, type = "info") {
    const status = card.querySelector(".model-card-status");
    status.textContent = message;
    status.className = `model-card-status is-${type}`;
  }

  function configureModelCard(model) {
    const fragment = modelCardTemplate.content.cloneNode(true);
    const card = fragment.querySelector(".model-card");
    card.dataset.modelKey = model.key;
    const image = card.querySelector(".model-card-image");
    const fallback = card.querySelector(".model-card-image-fallback");
    if (model.thumbnailUrl) {
      image.src = model.thumbnailUrl;
      image.alt = `${model.name} thumbnail`;
      image.addEventListener("error", () => {
        image.hidden = true;
        fallback.hidden = false;
      }, { once: true });
    } else {
      image.hidden = true;
      fallback.hidden = false;
    }

    card.querySelector(".model-card-name").textContent = model.name;
    const category = card.querySelector(".model-card-category");
    if (model.category) {
      category.hidden = false;
      category.textContent = model.category;
    }
    const price = card.querySelector(".model-card-price");
    if (model.price != null) {
      price.hidden = false;
      price.textContent = formattedPrice(model.price);
    }
    const description = card.querySelector(".model-card-description");
    if (model.description) {
      description.hidden = false;
      description.textContent = model.description;
    }
    const formats = [
      model.glbUrl && "GLB",
      model.usdzUrl && "USDZ",
      model.objUrl && "OBJ",
    ].filter(Boolean);
    card.querySelector(".model-card-formats").textContent = formats.length
      ? `Available: ${formats.join(" • ")}`
      : "No valid model files are available.";

    const view3d = card.querySelector(".library-view-3d");
    if (!model.glbUrl) {
      view3d.disabled = true;
      view3d.dataset.previewUnavailable = "true";
      view3d.title = "This record has no valid GLB file.";
      setModelCardStatus(card, "3D preview unavailable: no valid GLB file.", "error");
    }

    const iosAction = card.querySelector(".library-ios-ar-action");
    const arAction = card.querySelector(".library-ar-action");
    if (
      isIOS()
      && model.usdzUrl
      && secureExperienceAvailable()
      && isSecureAssetUrl(model.usdzUrl)
    ) {
      iosAction.href = model.usdzUrl;
      iosAction.hidden = false;
      arAction.hidden = true;
    }

    const details = card.querySelector(".model-card-details");
    let detailCount = 0;
    for (const [selector, text] of (
      [
        ["[data-detail-category]", model.category],
        ["[data-detail-dimensions]", model.dimensions && formattedDimensions(model.dimensions)],
        ["[data-detail-created]", model.createdAt && new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(model.createdAt))],
      ]
    )) {
      if (!text) continue;
      const row = details.querySelector(selector);
      row.hidden = false;
      row.querySelector("dd").textContent = text;
      detailCount += 1;
    }
    const objLink = card.querySelector(".model-card-obj-link");
    if (model.objUrl) {
      objLink.hidden = false;
      objLink.href = model.objUrl;
      objLink.rel = "noopener";
      detailCount += 1;
    }
    card.querySelector(".library-details-action").hidden = detailCount === 0;
    return fragment;
  }

  function populateCategoryFilter() {
    const categories = [...new Set(savedModels.map((model) => model.category).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b));
    const current = modelLibraryCategory.value;
    modelLibraryCategory.replaceChildren(new Option("All categories", ""));
    categories.forEach((category) => modelLibraryCategory.add(new Option(category, category)));
    modelLibraryCategory.value = categories.includes(current) ? current : "";
    modelLibraryCategoryWrap.hidden = categories.length === 0;
  }

  function renderModelLibrary() {
    if (!modelLibraryGrid) return;
    const query = modelLibrarySearch.value.trim().toLocaleLowerCase();
    const category = modelLibraryCategory.value;
    const visible = savedModels.filter((model) => (
      (!query || model.name.toLocaleLowerCase().includes(query))
      && (!category || model.category === category)
    ));
    modelLibraryGrid.replaceChildren(...visible.map(configureModelCard));
    modelLibraryGrid.hidden = visible.length === 0;
    modelLibraryEmpty.hidden = savedModels.length !== 0;
    modelLibraryNoResults.hidden = savedModels.length === 0 || visible.length !== 0;
    modelLibraryCount.hidden = false;
    modelLibraryCount.textContent = visible.length === savedModels.length
      ? `${savedModels.length} ${savedModels.length === 1 ? "model" : "models"}`
      : `${visible.length} of ${savedModels.length}`;
  }

  function showLibraryLoading({ preserveCards = false } = {}) {
    modelLibraryError.hidden = true;
    modelLibraryEmpty.hidden = true;
    modelLibraryNoResults.hidden = true;
    modelLibraryStatus.hidden = false;
    modelLibraryStatus.textContent = preserveCards ? "Refreshing saved models..." : "Loading saved models...";
    modelLibrarySkeletons.hidden = preserveCards;
    if (!preserveCards) modelLibraryGrid.hidden = true;
  }

  async function loadModelLibrary({ force = false } = {}) {
    if (!modelLibrary) return;
    if (modelLibraryPromise) return modelLibraryPromise;
    showLibraryLoading({ preserveCards: force && savedModels.length > 0 });
    modelLibraryPromise = (async () => {
      try {
        const response = await fetch("/api/models", {
          cache: "no-store",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        let payload = {};
        try {
          payload = await response.json();
        } catch (_error) {
          // A non-JSON upstream failure is handled with the status below.
        }
        if (!response.ok) {
          throw new Error(payload.detail || payload.error || `The server returned HTTP ${response.status}.`);
        }
        if (!Array.isArray(payload.models)) throw new Error("The server returned an invalid model list.");
        savedModels = payload.models.slice(0, 500)
          .map(normalizeSavedModel)
          .filter(Boolean);
        populateCategoryFilter();
        renderModelLibrary();
        modelLibrarySkeletons.hidden = true;
        modelLibraryStatus.hidden = true;
        modelLibraryError.hidden = true;
      } catch (error) {
        modelLibrarySkeletons.hidden = true;
        modelLibraryStatus.hidden = true;
        if (savedModels.length === 0) modelLibraryGrid.hidden = true;
        modelLibraryError.hidden = false;
        modelLibraryError.querySelector("[data-library-error-message]").textContent =
          `${error.message || "Please check the connection and try again."}`;
        console.error("[Model Library] fetch failed", error);
      } finally {
        modelLibraryPromise = null;
      }
    })();
    return modelLibraryPromise;
  }

  async function openSavedModelPreview(card, model) {
    if (!model.glbUrl) {
      setModelCardStatus(card, "3D preview unavailable: no valid GLB file.", "error");
      return;
    }
    setModelCardStatus(card, "Loading the saved GLB in the 3D viewer...");
    await loadPreview(modelLibrary, {
      type: "glb",
      url: model.glbUrl,
      downloadUrl: model.glbUrl,
      size: 0,
      label: model.name,
    });
    if (activePreviews.has(modelLibrary)) {
      setModelCardStatus(card, "3D preview loaded successfully.", "success");
    } else {
      setModelCardStatus(card, "The 3D preview could not be loaded. See the viewer error below.", "error");
    }
  }

  function launchSavedModelAR(card, model) {
    if (!secureExperienceAvailable()) {
      setModelCardStatus(card, "AR requires this app to be opened over HTTPS.", "error");
      return;
    }
    if (isAndroid()) {
      if (!model.glbUrl) {
        setModelCardStatus(card, "Android AR is unavailable: this model has no valid GLB file.", "error");
        return;
      }
      if (!isSecureAssetUrl(model.glbUrl)) {
        setModelCardStatus(card, "Android AR requires the GLB file to use HTTPS.", "error");
        return;
      }
      setModelCardStatus(card, "Opening Android Scene Viewer...");
      launchAndroidAR(model.glbUrl);
      return;
    }
    if (isIOS()) {
      setModelCardStatus(
        card,
        model.usdzUrl
          ? "iPhone/iPad AR requires the USDZ file to use HTTPS."
          : "iPhone/iPad AR is unavailable: this model has no valid USDZ file.",
        "error",
      );
      return;
    }
    setModelCardStatus(card, "Open this model library on Android or iPhone/iPad to use AR.");
  }

  function initializeAR(root) {
    const card = root.querySelector(".ar-card");
    if (!card || card.dataset.initialized) return;
    card.dataset.initialized = "true";
    const status = card.querySelector(".ar-status");
    const iosAction = card.querySelector(".ios-ar-action");
    const androidAction = card.querySelector(".android-ar-action");
    const unavailable = card.querySelector(".ar-unavailable");
    const secure = secureExperienceAvailable();

    if (card.dataset.dimensionsReady !== "true") {
      unavailable.hidden = false;
      unavailable.textContent = "Real dimensions required";
      status.textContent = "Apply real dimensions before opening AR.";
      return;
    }

    if (isIOS()) {
      if (iosAction && card.dataset.usdzReady === "true" && secure) {
        iosAction.hidden = false;
        status.textContent = "Ready for Apple Quick Look using the validated USDZ file.";
        iosAction.addEventListener("click", () => {
          status.textContent = "Opening Apple Quick Look. Close it to return to this page.";
          sessionStorage.setItem("furniture-ar-launched", "true");
        });
      } else {
        unavailable.hidden = false;
        status.textContent = secure
          ? "iPhone AR file is not available for this model. GLB download and preview are still available."
          : "iPhone AR requires this page to be opened over HTTPS.";
      }
      return;
    }

    if (isAndroid()) {
      const modelUrl = androidAction?.dataset.modelUrl;
      if (androidAction && modelUrl && secure && isSecureAssetUrl(new URL(modelUrl, location.href).href)) {
        androidAction.hidden = false;
        status.textContent = "Ready for Android Scene Viewer. If unavailable, you will return to this page.";
        androidAction.addEventListener("click", () => {
          launchAndroidAR(new URL(modelUrl, location.href).href);
        });
      } else {
        unavailable.hidden = false;
        status.textContent = secure ? "Android AR is unavailable for this model." : "Android AR requires HTTPS.";
      }
      return;
    }

    unavailable.hidden = false;
    status.textContent = "Desktop preview is available. AR controls appear only on supported phones.";
  }

  function initializeResult(root) {
    const previewRoot = root.matches?.("[data-preview-root]") ? root : root.querySelector?.("[data-preview-root]");
    if (!previewRoot || previewRoot.dataset.initialized) return;
    previewRoot.dataset.initialized = "true";
    window.FurnitureDimensions?.initialize(previewRoot);
    initializeAR(previewRoot);
    setProductSaveAvailability(false);
    previewRoot.querySelectorAll(".preview-trigger").forEach((button) => {
      button.addEventListener("click", () => loadPreview(previewRoot, {
        type: button.dataset.previewType,
        url: button.dataset.previewUrl,
        downloadUrl: button.dataset.downloadUrl,
        size: Number(button.dataset.fileSize) || 0,
      }));
    });
    previewRoot.querySelector(".unload-preview")?.addEventListener("click", () => unloadPreview(previewRoot));
    previewRoot.querySelector(".retry-preview")?.addEventListener("click", () => {
      const retry = previewRoot.querySelector(".retry-preview");
      if (retry.dataset.previewUrl) loadPreview(previewRoot, {
        type: retry.dataset.previewType,
        url: retry.dataset.previewUrl,
        downloadUrl: retry.dataset.downloadUrl,
        size: Number(retry.dataset.fileSize) || 0,
      });
    });
  }

  function apiErrorMessage(payload, fallback) {
    const detail = payload?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const messages = detail.map((entry) => {
        const location = Array.isArray(entry?.loc)
          ? entry.loc.filter((part) => part !== "body").join(".")
          : "";
        const message = typeof entry?.msg === "string" && entry.msg.trim()
          ? entry.msg
          : "Invalid value.";
        return location ? `${location}: ${message}` : message;
      });
      if (messages.length) return messages.join(" ");
    }
    if (typeof payload?.error === "string" && payload.error.trim()) return payload.error;
    return fallback;
  }

  function buildConversionFormData() {
    const selectedImage = imageInput?.files?.[0];
    if (!selectedImage) {
      throw new Error("Please reselect a PNG, JPEG, or WebP image before converting.");
    }

    const formData = new FormData(form);
    formData.set("image", selectedImage, selectedImage.name);
    const removeBackground = form.querySelector(
      'input[name="remove_background"][type="checkbox"]',
    );
    const preserveDetails = form.querySelector(
      'input[name="preserve_details"][type="checkbox"]',
    );
    formData.set("remove_background", removeBackground?.checked ? "true" : "false");
    formData.set("preserve_details", preserveDetails?.checked ? "true" : "false");
    formData.set("quality_mode", qualityMode?.checked ? "true" : "false");
    return formData;
  }

  function uploadConversion(formData, signal) {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", "/api/conversions");
      request.responseType = "json";
      request.setRequestHeader("Accept", "application/json");
      request.upload.addEventListener("progress", (event) => {
        if (!event.lengthComputable || event.total <= 0) return;
        setConversionProgress(
          "Uploading image...",
          Math.max(1, Math.min(8, (event.loaded / event.total) * 8)),
        );
      });
      request.addEventListener("load", () => {
        const payload = request.response && typeof request.response === "object"
          ? request.response
          : {};
        if (request.status >= 200 && request.status < 300) {
          resolve(payload);
          return;
        }
        reject(new Error(apiErrorMessage(
          payload,
          `The server returned HTTP ${request.status}.`,
        )));
      });
      request.addEventListener("error", () => reject(new Error("The image upload could not reach the server.")));
      request.addEventListener("abort", () => reject(new DOMException("Conversion request cancelled.", "AbortError")));
      signal.addEventListener("abort", () => request.abort(), { once: true });
      request.send(formData);
    });
  }

  function sameOriginUrl(value) {
    const url = new URL(value, location.origin);
    if (url.origin !== location.origin) throw new Error("The server returned an unsafe conversion URL.");
    return url.href;
  }

  async function pollConversion(statusUrl, signal) {
    let networkFailures = 0;
    while (!signal.aborted) {
      try {
        const response = await fetch(sameOriginUrl(statusUrl), {
          cache: "no-store",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
          signal,
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(apiErrorMessage(
            payload,
            `Status request failed with HTTP ${response.status}.`,
          ));
        }
        networkFailures = 0;
        setConversionProgress(payload.message || "Converting image to 3D...", Number(payload.progress) || 0);
        if (payload.status === "failed") {
          const suffix = payload.error_reference ? ` Reference: ${payload.error_reference}.` : "";
          throw new Error(`${payload.error || "3D conversion failed."}${suffix}`);
        }
        if (payload.status === "complete") {
          const resultResponse = await fetch(sameOriginUrl(payload.result_url), {
            cache: "no-store",
            credentials: "same-origin",
            headers: { Accept: "text/html" },
            signal,
          });
          if (!resultResponse.ok) {
            throw new Error(`The conversion finished, but the result returned HTTP ${resultResponse.status}.`);
          }
          const oldRoot = conversionResult.querySelector("[data-preview-root]");
          if (oldRoot) unloadPreview(oldRoot);
          conversionResult.innerHTML = await resultResponse.text();
          conversionResult.classList.remove("empty-state");
          window.htmx?.process(conversionResult);
          initializeResult(conversionResult);
          conversionResult.scrollIntoView({ behavior: "smooth", block: "start" });
          return;
        }
      } catch (error) {
        if (error.name === "AbortError") throw error;
        networkFailures += 1;
        if (networkFailures >= 5 || /conversion failed|unsafe conversion URL|finished, but/i.test(error.message)) {
          throw error;
        }
        setConversionProgress("Connection interrupted. Reconnecting to conversion...", null);
      }
      await new Promise((resolve) => window.setTimeout(resolve, networkFailures ? 1200 : 650));
    }
    throw new DOMException("Conversion polling cancelled.", "AbortError");
  }

  function showConversionError(message) {
    const notice = document.createElement("div");
    notice.className = "notice notice-error";
    notice.setAttribute("role", "alert");
    notice.textContent = message;
    conversionResult.replaceChildren(notice);
    conversionResult.classList.remove("empty-state");
  }

  async function startProgressiveConversion(event) {
    event.preventDefault();
    if (!form.reportValidity()) return;
    conversionPollController?.abort();
    conversionPollController = new AbortController();
    const { signal } = conversionPollController;
    setConversionLocked(true);
    progressPanel.hidden = false;
    startConversionTimer();
    setConversionProgress("Preparing image upload...", 0);
    notify(
      qualityMode?.checked
        ? "Generating three quality variants. This takes longer."
        : "Starting fast single-model conversion...",
      "info",
    );

    try {
      const job = await uploadConversion(buildConversionFormData(), signal);
      if (!job.status_url) throw new Error("The server did not return a conversion status URL.");
      setConversionProgress("Upload complete. Starting conversion...", 8);
      await pollConversion(job.status_url, signal);
      setConversionProgress("3D model generated and validated", 100);
      notify("3D model generated successfully.", "success");
    } catch (error) {
      if (error.name === "AbortError") return;
      setConversionProgress("Conversion failed. See the error below.", null);
      showConversionError(error.message || "3D conversion failed.");
      notify("3D conversion failed.", "error");
    } finally {
      if (conversionPollController?.signal === signal) conversionPollController = null;
      stopConversionTimer();
      setConversionLocked(false);
    }
  }

  function markReturnedFromAR() {
    if (sessionStorage.getItem("furniture-ar-launched") === "true") {
      document.querySelectorAll(".ar-status").forEach((status) => {
        status.textContent = "Returned to this product page from AR.";
      });
      sessionStorage.removeItem("furniture-ar-launched");
    }
  }

  updateDeviceSummary();
  initializeResult(document);
  loadModelLibrary();
  modelLibrarySearch?.addEventListener("input", renderModelLibrary);
  modelLibraryCategory?.addEventListener("change", renderModelLibrary);
  document.getElementById("model-library-retry")?.addEventListener("click", () => loadModelLibrary({ force: true }));
  modelLibrary?.querySelector(".unload-preview")?.addEventListener("click", () => unloadPreview(modelLibrary));
  modelLibrary?.querySelector(".retry-preview")?.addEventListener("click", () => {
    const retry = modelLibrary.querySelector(".retry-preview");
    if (retry.dataset.previewUrl) loadPreview(modelLibrary, {
      type: retry.dataset.previewType,
      url: retry.dataset.previewUrl,
      downloadUrl: retry.dataset.downloadUrl,
      size: Number(retry.dataset.fileSize) || 0,
      label: retry.dataset.previewLabel,
    });
  });
  modelLibraryGrid?.addEventListener("click", (event) => {
    const card = event.target.closest(".model-card");
    if (!card) return;
    const model = savedModels.find((candidate) => candidate.key === card.dataset.modelKey);
    if (!model) return;
    if (event.target.closest(".library-view-3d")) {
      openSavedModelPreview(card, model);
      return;
    }
    if (event.target.closest(".library-ios-ar-action")) {
      setModelCardStatus(card, "Opening Apple Quick Look. Close it to return to this page.");
      sessionStorage.setItem("furniture-ar-launched", "true");
      return;
    }
    if (event.target.closest(".library-ar-action")) {
      launchSavedModelAR(card, model);
      return;
    }
    const detailsAction = event.target.closest(".library-details-action");
    if (detailsAction) {
      const details = card.querySelector(".model-card-details");
      details.hidden = !details.hidden;
      detailsAction.setAttribute("aria-expanded", String(!details.hidden));
      detailsAction.textContent = details.hidden ? "View Details" : "Hide Details";
    }
  });
  window.addEventListener("pageshow", markReturnedFromAR);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") markReturnedFromAR();
  });

  imageInput.addEventListener("change", () => {
    if (imageInput.files.length) notify("Image ready for conversion.", "success");
  });
  form.addEventListener("submit", startProgressiveConversion);

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    if (event.detail.xhr.status >= 400) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
    const oldRoot = event.detail.target.querySelector?.("[data-preview-root]");
    if (oldRoot) unloadPreview(oldRoot);
  });

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    if (event.detail.elt.closest("#product-form") || event.detail.elt.getAttribute("form") === "product-form") {
      document.querySelectorAll('[form="product-form"]').forEach((button) => { button.disabled = true; });
      if (saveButton) saveButton.textContent = "Saving...";
    }
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    if (event.detail.elt.closest("#product-form") || event.detail.elt.getAttribute("form") === "product-form") {
      document.querySelectorAll('[form="product-form"]').forEach((button) => {
        button.disabled = event.detail.successful;
      });
      if (saveButton) saveButton.textContent = "Save to Supabase";
      notify(
        event.detail.successful ? "Saved to Supabase successfully." : "Supabase save failed.",
        event.detail.successful ? "success" : "error",
      );
      if (event.detail.successful) loadModelLibrary({ force: true });
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => initializeResult(event.detail.target));

  window.addEventListener("pagehide", () => {
    conversionPollController?.abort();
    activePreviews.forEach((_value, root) => unloadPreview(root));
  });

  window.addEventListener("offline", () => {
    notify("You are offline. Conversion, saving, and AR assets require a connection.", "info");
  });
  window.addEventListener("online", () => {
    notify("Connection restored.", "success");
  });
  if (!navigator.onLine) {
    notify("You are offline. Conversion, saving, and AR assets require a connection.", "info");
  }

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", async () => {
      try {
        const registration = await navigator.serviceWorker.register("/service-worker.js", {
          scope: "/",
          updateViaCache: "none",
        });
        const observeWorker = (worker) => {
          if (!worker) return;
          worker.addEventListener("statechange", () => {
            if (worker.state === "installed" && navigator.serviceWorker.controller) {
              console.info("[Furniture AR] app update installed");
              notify("An app update is ready. Refresh after finishing your current work.", "info");
            }
          });
        };
        observeWorker(registration.installing);
        registration.addEventListener("updatefound", () => observeWorker(registration.installing));
        navigator.serviceWorker.addEventListener("controllerchange", () => {
          console.info("[Furniture AR] service worker controller updated");
        });
        registration.update().catch((error) => {
          console.warn("[Furniture AR] service worker update check failed", error);
        });
      } catch (error) {
        console.warn("[Furniture AR] service worker registration failed", error);
      }
    });
  } else {
    console.info("[Furniture AR] service workers are not supported in this browser");
  }
})();
