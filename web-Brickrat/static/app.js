(() => {
  const form = document.getElementById("conversion-form");
  const imageInput = document.getElementById("image-input");
  const convertButton = document.getElementById("convert-button");
  const saveButton = document.getElementById("save-button");
  const progressPanel = document.getElementById("conversion-progress");
  const progressBar = document.getElementById("progress-bar");
  const progressStatus = document.getElementById("progress-status");
  const progressPercent = document.getElementById("progress-percent");
  let timer;

  function renderProgress(value, status) {
    progressBar.value = value;
    progressBar.textContent = `${value}%`;
    progressPercent.textContent = `${value}%`;
    progressStatus.textContent = status;
  }

  function setConversionLocked(locked) {
    imageInput.disabled = locked;
    convertButton.disabled = locked;
  }

  function initializeModelViewerStatus(root = document) {
    root.querySelectorAll(".ar-model-viewer").forEach((viewer) => {
      if (viewer.dataset.statusInitialized) return;
      viewer.dataset.statusInitialized = "true";
      const error = viewer.parentElement.querySelector(".model-error");
      viewer.addEventListener("load", () => {
        if (error) error.hidden = true;
      });
      viewer.addEventListener("error", () => {
        if (error) error.hidden = false;
      });
    });
  }

  initializeModelViewerStatus();

  form.addEventListener("htmx:beforeRequest", () => {
    setConversionLocked(true);
    saveButton.disabled = true;
    progressPanel.hidden = false;
    renderProgress(5, "Uploading image...");
    let value = 5;
    timer = window.setInterval(() => {
      value = Math.min(value + (value < 35 ? 5 : value < 70 ? 2 : 1), 92);
      const status = value < 25 ? "Uploading image..."
        : value < 50 ? "Removing and preparing background..."
        : value < 80 ? "Converting to 3D..."
        : "Generating model files...";
      renderProgress(value, status);
    }, 700);
  });

  form.addEventListener("htmx:afterRequest", (event) => {
    window.clearInterval(timer);
    setConversionLocked(false);
    renderProgress(
      event.detail.successful ? 100 : 0,
      event.detail.successful ? "Conversion completed" : "Conversion failed",
    );
  });

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    if (event.detail.xhr.status >= 400) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    if (event.detail.elt.closest("#product-form")) {
      saveButton.disabled = true;
      saveButton.textContent = "Saving...";
    }
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    if (event.detail.elt.closest("#product-form")) {
      saveButton.disabled = event.detail.successful;
      saveButton.textContent = "Save to Supabase";
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    initializeModelViewerStatus(event.detail.target);
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js").catch(() => {});
    });
  }
})();
