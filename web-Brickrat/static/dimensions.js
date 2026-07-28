(() => {
  const UNIT_TO_METRES = Object.freeze({
    cm: 0.01,
    mm: 0.001,
    m: 1,
    in: 0.0254,
    ft: 0.3048,
  });

  const STATUS_LABELS = Object.freeze({
    fits: "Fits in room",
    fits_after_rotation: "Fits only after rotation",
    does_not_fit: "Does not fit",
  });

  function positiveValue(input, label) {
    const value = Number(input?.value);
    if (!Number.isFinite(value) || value <= 0) {
      input?.focus();
      throw new Error(`${label} must be a positive number.`);
    }
    return value;
  }

  function fitFurniture(furniture, room, placement = null) {
    const areaWidth = placement?.width_m ?? room.width_m;
    const areaDepth = placement?.depth_m ?? room.length_m;
    const direct = {
      width_m: areaWidth - furniture.width_m,
      depth_m: areaDepth - furniture.depth_m,
      height_m: room.height_m - furniture.height_m,
    };
    const rotated = {
      width_m: areaWidth - furniture.depth_m,
      depth_m: areaDepth - furniture.width_m,
      height_m: room.height_m - furniture.height_m,
    };
    const fits = (clearance) => Math.min(...Object.values(clearance)) >= -1e-9;
    const directFits = fits(direct);
    const rotatedFits = fits(rotated);

    if (directFits) {
      return { status: "fits", orientation: "width_x_depth", clearance: direct };
    }
    if (rotatedFits) {
      return {
        status: "fits_after_rotation",
        orientation: "depth_x_width",
        clearance: rotated,
      };
    }
    const directScore = Math.min(...Object.values(direct));
    const rotatedScore = Math.min(...Object.values(rotated));
    return rotatedScore > directScore
      ? { status: "does_not_fit", orientation: "depth_x_width", clearance: rotated }
      : { status: "does_not_fit", orientation: "width_x_depth", clearance: direct };
  }

  function roomData(ui) {
    const unitInput = ui.querySelector("[data-room-field='unit']");
    const unit = unitInput?.value;
    const multiplier = UNIT_TO_METRES[unit];
    if (!multiplier) throw new Error("Choose a valid room unit.");
    const width = positiveValue(ui.querySelector("[data-room-field='width']"), "Room width");
    const length = positiveValue(ui.querySelector("[data-room-field='length']"), "Room length");
    const height = positiveValue(ui.querySelector("[data-room-field='height']"), "Room height");
    const placementWidthInput = ui.querySelector("[data-room-field='placement_width']");
    const placementDepthInput = ui.querySelector("[data-room-field='placement_depth']");
    const hasPlacementWidth = placementWidthInput?.value.trim() !== "";
    const hasPlacementDepth = placementDepthInput?.value.trim() !== "";
    if (hasPlacementWidth !== hasPlacementDepth) {
      throw new Error("Enter both placement-area width and depth, or leave both blank.");
    }
    const placement = hasPlacementWidth
      ? {
        width_m: positiveValue(placementWidthInput, "Placement-area width") * multiplier,
        depth_m: positiveValue(placementDepthInput, "Placement-area depth") * multiplier,
      }
      : null;
    return {
      unit,
      room: {
        width_m: width * multiplier,
        length_m: length * multiplier,
        height_m: height * multiplier,
      },
      placement,
    };
  }

  function formatDistance(metres, unit) {
    const value = metres / UNIT_TO_METRES[unit];
    const digits = Math.abs(value) >= 100 ? 1 : Math.abs(value) >= 10 ? 2 : 3;
    return `${value.toFixed(digits)} ${unit}`;
  }

  function renderFit(ui) {
    const output = ui.querySelector("[data-fit-result]");
    try {
      const furniture = {
        width_m: Number(ui.dataset.finalWidthM),
        height_m: Number(ui.dataset.finalHeightM),
        depth_m: Number(ui.dataset.finalDepthM),
      };
      if (!Object.values(furniture).every((value) => Number.isFinite(value) && value > 0)) {
        throw new Error("Apply furniture dimensions first.");
      }
      const { unit, room, placement } = roomData(ui);
      const result = fitFurniture(furniture, room, placement);
      const orientation = result.orientation === "width_x_depth"
        ? "Width x depth"
        : "Rotated depth x width";
      const clearanceRows = Object.entries(result.clearance).map(([axis, value]) => {
        const label = axis.replace("_m", "");
        const kind = value >= -1e-9 ? "clearance" : "shortage";
        return `<li><span>${label}</span><strong class="${kind}">${formatDistance(value, unit)}</strong></li>`;
      }).join("");
      output.className = `fit-result fit-${result.status}`;
      output.innerHTML = `
        <strong>${STATUS_LABELS[result.status]}</strong>
        <span>${orientation}${placement ? " in the selected placement area" : ""}</span>
        <ul aria-label="Remaining clearance">${clearanceRows}</ul>
      `;
    } catch (error) {
      output.className = "fit-result fit-error";
      output.textContent = error.message;
    }
  }

  function storageKey(ui) {
    return `furniture-room-dimensions:${ui.dataset.conversionId}`;
  }

  function saveRoomDraft(ui) {
    const values = {};
    ui.querySelectorAll("[data-room-field]").forEach((input) => {
      values[input.dataset.roomField] = input.value;
    });
    try {
      sessionStorage.setItem(storageKey(ui), JSON.stringify(values));
    } catch (_error) {
      // Private browsing or storage policy can disable sessionStorage.
    }
  }

  function restoreRoomDraft(ui) {
    let values;
    try {
      values = JSON.parse(sessionStorage.getItem(storageKey(ui)) || "null");
    } catch (_error) {
      values = null;
    }
    if (!values || typeof values !== "object") return;
    ui.querySelectorAll("[data-room-field]").forEach((input) => {
      const value = values[input.dataset.roomField];
      if (typeof value === "string") input.value = value;
    });
  }

  function setMeasuredValue(ui, fieldName, metres) {
    const unit = ui.querySelector("[data-room-field='unit']")?.value || "m";
    const input = ui.querySelector(`[data-room-field='${fieldName}']`);
    if (!input || !Number.isFinite(metres) || metres <= 0) return;
    input.value = (metres / UNIT_TO_METRES[unit]).toFixed(3).replace(/\.?0+$/, "");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function pointDistance(first, second) {
    return Math.hypot(
      second.x - first.x,
      second.y - first.y,
      second.z - first.z,
    );
  }

  function applyCornerMeasurements(ui, points) {
    if (points.length < 3) throw new Error("Mark at least three floor corners.");
    if (points.length >= 4) {
      const distances = [
        pointDistance(points[0], points[1]),
        pointDistance(points[1], points[2]),
        pointDistance(points[2], points[3]),
        pointDistance(points[3], points[0]),
      ];
      const firstPair = (distances[0] + distances[2]) / 2;
      const secondPair = (distances[1] + distances[3]) / 2;
      setMeasuredValue(ui, "width", Math.max(firstPair, secondPair));
      setMeasuredValue(ui, "length", Math.min(firstPair, secondPair));
      return;
    }
    setMeasuredValue(ui, "width", pointDistance(points[0], points[1]));
    setMeasuredValue(ui, "length", pointDistance(points[1], points[2]));
  }

  function createMeasurementOverlay() {
    const overlay = document.createElement("div");
    overlay.className = "xr-measure-overlay";
    overlay.innerHTML = `
      <div class="xr-reticle" aria-hidden="true"></div>
      <section class="xr-measure-controls">
        <strong>AR room measurement</strong>
        <span data-xr-status>Aim the centre marker at a floor or wall surface.</span>
        <span data-xr-count>0 points marked</span>
        <div class="button-row">
          <button class="button primary" type="button" data-xr-mark>Mark point</button>
          <button class="button outline" type="button" data-xr-undo>Undo</button>
          <button class="button secondary" type="button" data-xr-finish>Finish</button>
        </div>
      </section>
    `;
    overlay.addEventListener("beforexrselect", (event) => event.preventDefault());
    document.body.appendChild(overlay);
    return overlay;
  }

  async function startWebXRMeasurement(ui) {
    const support = ui.querySelector("[data-ar-measure-support]");
    const startButton = ui.querySelector("[data-ar-measure-start]");
    const target = ui.querySelector("[data-measure-target]")?.value || "width";
    const overlay = createMeasurementOverlay();
    const status = overlay.querySelector("[data-xr-status]");
    const count = overlay.querySelector("[data-xr-count]");
    const canvas = document.createElement("canvas");
    canvas.className = "xr-render-surface";
    document.body.appendChild(canvas);
    startButton.disabled = true;

    let session;
    let hitTestSource;
    let latestHit = null;
    let referenceSpace;
    const points = [];

    const updateCount = () => {
      count.textContent = `${points.length} point${points.length === 1 ? "" : "s"} marked`;
    };
    const applyTwoPointMeasurement = () => {
      if (points.length < 2) throw new Error("Mark two points before finishing.");
      setMeasuredValue(ui, target, pointDistance(points[0], points[1]));
    };
    const finish = async () => {
      try {
        if (target === "corners") applyCornerMeasurements(ui, points);
        else applyTwoPointMeasurement();
        support.textContent = "Measurement captured. Review or correct the room values before saving.";
      } catch (error) {
        status.textContent = error.message;
        return;
      }
      await session?.end();
    };
    const markPoint = () => {
      if (!latestHit) {
        status.textContent = "No surface is detected at the centre marker yet. Move slowly and try again.";
        return;
      }
      points.push({ ...latestHit });
      updateCount();
      if (points.length > 1) {
        const distance = pointDistance(points.at(-2), points.at(-1));
        status.textContent = `Segment measured: ${distance.toFixed(3)} m.`;
      } else {
        status.textContent = "First point marked. Aim at the next point.";
      }
      if (target !== "corners" && points.length === 2) finish();
      if (target === "corners" && points.length === 4) finish();
    };

    overlay.querySelector("[data-xr-mark]").addEventListener("click", markPoint);
    overlay.querySelector("[data-xr-undo]").addEventListener("click", () => {
      points.pop();
      updateCount();
      status.textContent = "Last point removed.";
    });
    overlay.querySelector("[data-xr-finish]").addEventListener("click", finish);

    try {
      const options = {
        requiredFeatures: ["hit-test"],
        optionalFeatures: ["local-floor", "dom-overlay"],
        domOverlay: { root: overlay },
      };
      try {
        session = await navigator.xr.requestSession("immersive-ar", options);
      } catch (_firstError) {
        session = await navigator.xr.requestSession("immersive-ar", {
          requiredFeatures: ["hit-test"],
          optionalFeatures: ["local-floor"],
        });
      }
      const gl = canvas.getContext("webgl", { xrCompatible: true, alpha: true });
      if (!gl) throw new Error("WebGL is unavailable for the AR measurement session.");
      await gl.makeXRCompatible?.();
      session.updateRenderState({ baseLayer: new XRWebGLLayer(session, gl) });
      try {
        referenceSpace = await session.requestReferenceSpace("local-floor");
      } catch (_error) {
        referenceSpace = await session.requestReferenceSpace("local");
      }
      const viewerSpace = await session.requestReferenceSpace("viewer");
      try {
        hitTestSource = await session.requestHitTestSource({
          space: viewerSpace,
          entityTypes: ["plane"],
        });
      } catch (_error) {
        hitTestSource = await session.requestHitTestSource({ space: viewerSpace });
      }
      session.addEventListener("select", markPoint);
      session.addEventListener("end", () => {
        hitTestSource?.cancel?.();
        overlay.remove();
        canvas.remove();
        startButton.disabled = false;
      }, { once: true });

      const onFrame = (_time, frame) => {
        session.requestAnimationFrame(onFrame);
        latestHit = null;
        const results = frame.getHitTestResults(hitTestSource);
        const pose = results[0]?.getPose(referenceSpace);
        if (pose) {
          const { x, y, z } = pose.transform.position;
          latestHit = { x, y, z };
          if (points.length === 0) status.textContent = "Surface detected. Mark the first point.";
        }
        const layer = session.renderState.baseLayer;
        gl.bindFramebuffer(gl.FRAMEBUFFER, layer.framebuffer);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      };
      session.requestAnimationFrame(onFrame);
    } catch (error) {
      overlay.remove();
      canvas.remove();
      startButton.disabled = false;
      support.textContent = `AR measurement is unavailable: ${error.message}`;
      support.classList.add("warning");
      ui.querySelector("[data-ar-measure-controls]").hidden = true;
      try { await session?.end(); } catch (_endError) { /* session already closed */ }
    }
  }

  async function detectWebXR(ui) {
    const support = ui.querySelector("[data-ar-measure-support]");
    const controls = ui.querySelector("[data-ar-measure-controls]");
    if (!window.isSecureContext || !navigator.xr || typeof XRWebGLLayer === "undefined") {
      support.textContent = window.isSecureContext
        ? "WebXR measurement is not available in this browser. Use manual room dimensions."
        : "WebXR measurement requires HTTPS. Use manual room dimensions on this page.";
      controls.hidden = true;
      return;
    }
    try {
      const supported = await navigator.xr.isSessionSupported("immersive-ar");
      controls.hidden = !supported;
      support.textContent = supported
        ? "This device reports immersive AR support. The session will also verify hit testing."
        : "This device does not report immersive AR support. Use manual room dimensions.";
    } catch (_error) {
      controls.hidden = true;
      support.textContent = "AR capability could not be confirmed. Use manual room dimensions.";
    }
  }

  function initialize(root = document) {
    const ui = root.matches?.("[data-dimensions-ui]")
      ? root
      : root.querySelector?.("[data-dimensions-ui]");
    if (!ui || ui.dataset.dimensionsInitialized === "true") return;
    ui.dataset.dimensionsInitialized = "true";
    restoreRoomDraft(ui);
    ui.querySelectorAll("[data-room-field]").forEach((input) => {
      input.addEventListener("input", () => saveRoomDraft(ui));
      input.addEventListener("change", () => saveRoomDraft(ui));
    });
    ui.querySelector("[data-fit-check]")?.addEventListener("click", () => renderFit(ui));
    ui.querySelector("[data-ar-measure-start]")?.addEventListener(
      "click", () => startWebXRMeasurement(ui),
    );
    detectWebXR(ui);
  }

  window.FurnitureDimensions = Object.freeze({
    initialize,
    fitFurniture,
    UNIT_TO_METRES,
  });
})();
