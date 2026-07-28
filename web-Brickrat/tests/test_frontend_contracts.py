import json
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    def test_manifest_has_installable_icons(self):
        manifest = json.loads((ROOT / "static" / "manifest.json").read_text(encoding="utf-8"))
        for field in (
            "name", "short_name", "description", "start_url", "scope", "display",
            "orientation", "theme_color", "background_color", "icons",
        ):
            self.assertTrue(manifest.get(field), field)
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        sizes = {icon["sizes"] for icon in manifest["icons"]}
        self.assertIn("192x192", sizes)
        self.assertIn("512x512", sizes)
        self.assertTrue(any("maskable" in icon.get("purpose", "") for icon in manifest["icons"]))
        for icon in manifest["icons"]:
            self.assertTrue((ROOT / "static" / icon["src"].removeprefix("/static/")).is_file())
        for filename, expected_size in (("icon-192.png", (192, 192)), ("icon-512.png", (512, 512))):
            with Image.open(ROOT / "static" / "icons" / filename) as image:
                self.assertEqual(image.size, expected_size)

    def test_result_uses_direct_validated_usdz_quick_look_link(self):
        template = (ROOT / "templates" / "conversion_result.html").read_text(encoding="utf-8")
        self.assertEqual(template.count('rel="ar"'), 1)
        self.assertIn('href="{{ usdz_url }}"', template)
        self.assertIn("{% if usdz_url %}", template)
        self.assertIn('class="button primary android-ar-action"', template)

    def test_page_has_installable_metadata_and_does_not_eager_load_viewer_modules(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"', page)
        for marker in (
            'rel="manifest"', 'name="theme-color"',
            'name="apple-mobile-web-app-capable"',
            'name="apple-mobile-web-app-status-bar-style"',
            'name="apple-mobile-web-app-title"', 'rel="apple-touch-icon"',
            'rel="icon"',
        ):
            self.assertIn(marker, page)
        self.assertEqual(page.count('name="theme-color"'), 1)
        self.assertEqual(page.count('rel="manifest"'), 1)
        self.assertNotIn("model-viewer.min.js", page)
        self.assertNotIn("obj-preview.js", page)

    def test_previews_are_on_demand_and_recoverable(self):
        template = (ROOT / "templates" / "conversion_result.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("<model-viewer", template)
        self.assertNotIn('class="obj-preview"', template)
        self.assertIn("Load GLB Preview", template)
        self.assertIn("Load OBJ Preview", template)
        self.assertIn("Retry preview", template)
        self.assertIn("Download model", template)
        self.assertIn('button.addEventListener("click", () => loadPreview', script)
        self.assertIn("unloadPreview(root, { hide: false })", script)
        self.assertIn("URL.revokeObjectURL", script)

    def test_quality_mode_exposes_three_selectable_candidates(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        template = (ROOT / "templates" / "conversion_result.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('name="quality_mode"', page)
        self.assertIn("Compare 3 quality variants", page)
        self.assertNotIn('id="quality-mode" name="quality_mode" type="checkbox" value="true" checked', page)
        self.assertIn("<option selected>256</option>", page)
        self.assertIn("About 3&times; more export work", page)
        self.assertIn("Choose the best geometry", template)
        self.assertIn('hx-post="/conversions/{{ conversion_id }}/candidate"', template)
        self.assertIn("candidate.preview_url", template)
        self.assertIn("existing?.url === url", script)
        self.assertIn("retry.dataset.previewUrl", script)

    def test_conversion_uses_background_progress_api_with_elapsed_time_and_fallback(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('action="/convert"', page)
        self.assertIn('method="post"', page)
        self.assertIn('enctype="multipart/form-data"', page)
        self.assertIn('id="progress-percent">0%</strong>', page)
        self.assertIn('id="progress-elapsed">Elapsed 0s</small>', page)
        self.assertIn('request.open("POST", "/api/conversions")', script)
        self.assertIn('request.upload.addEventListener("progress"', script)
        self.assertIn("async function pollConversion", script)
        self.assertIn("payload.progress", script)
        self.assertIn("setInterval(updateConversionElapsed, 1000)", script)
        self.assertIn('form.addEventListener("submit", startProgressiveConversion)', script)
        self.assertIn("function buildConversionFormData()", script)
        self.assertIn('formData.set("image", selectedImage, selectedImage.name)', script)
        self.assertIn("function apiErrorMessage(payload, fallback)", script)
        self.assertIn("Array.isArray(detail)", script)

    def test_mobile_css_prevents_horizontal_overflow_and_has_touch_targets(self):
        styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("overflow-x: hidden", styles)
        self.assertIn("@media (max-width: 767px)", styles)
        self.assertIn("min-height: 48px", styles)

    def test_service_worker_does_not_cache_generated_models(self):
        worker = (ROOT / "static" / "service-worker.js").read_text(encoding="utf-8")
        self.assertIn('url.pathname.startsWith("/generated/")', worker)
        self.assertIn('url.pathname.startsWith("/models/")', worker)
        self.assertIn('url.pathname.startsWith("/api/")', worker)
        self.assertIn('cache: "no-store"', worker)

    def test_service_worker_has_versioned_shell_strategies_and_offline_fallback(self):
        worker = (ROOT / "static" / "service-worker.js").read_text(encoding="utf-8")
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('const CACHE_NAME = `${CACHE_PREFIX}__ASSET_VERSION__`', worker)
        self.assertIn('const OFFLINE_URL = "/static/offline.html"', worker)
        self.assertIn("async function cacheFirst", worker)
        self.assertIn("async function networkFirstNavigation", worker)
        self.assertIn('url.pathname.startsWith("/static/")', worker)
        self.assertTrue((ROOT / "static" / "offline.html").is_file())
        self.assertIn('window.addEventListener("load", async () =>', script)
        self.assertIn('navigator.serviceWorker.register("/service-worker.js"', script)
        self.assertIn('registration.addEventListener("updatefound"', script)
        self.assertIn('navigator.serviceWorker.addEventListener("controllerchange"', script)

    def test_dimensions_ui_and_capability_gated_measurement_are_present(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        template = (ROOT / "templates" / "conversion_result.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "dimensions.js").read_text(encoding="utf-8")
        self.assertIn("path='/dimensions.js'", page)
        for label in (
            "Model Dimensions", "Scaling Mode", "Final Dimensions",
            "Room Dimensions", "AR Measure Room", "Check Furniture Fit",
        ):
            self.assertIn(label, template)
        self.assertIn('name="scaling_mode"', template)
        self.assertIn("Reset to original scale", template)
        self.assertIn("X = width, Y = height, Z = depth", template)
        self.assertIn('isSessionSupported("immersive-ar")', script)
        self.assertIn('requiredFeatures: ["hit-test"]', script)
        self.assertIn("controls.hidden = !supported", script)
        self.assertIn("RoomPlan", template)

    def test_fit_ui_exposes_all_required_outcomes_and_orientations(self):
        script = (ROOT / "static" / "dimensions.js").read_text(encoding="utf-8")
        for marker in (
            "Fits in room", "Does not fit", "Fits only after rotation",
            "width_x_depth", "depth_x_width", "clearance",
        ):
            self.assertIn(marker, script)

    def test_model_library_has_search_cards_loading_and_empty_states(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        for marker in (
            "Model Library", 'id="model-library-search"',
            'id="model-library-category-wrap"', 'id="model-library-skeletons"',
            'id="model-library-empty"', 'id="model-card-template"',
            "View in 3D", "View in AR", "View Details",
        ):
            self.assertIn(marker, page)
        self.assertIn('fetch("/api/models"', script)
        self.assertIn("if (modelLibraryPromise) return modelLibraryPromise", script)
        self.assertIn("model.name.toLocaleLowerCase().includes(query)", script)
        self.assertIn(".model-card-grid", styles)
        self.assertIn("repeat(auto-fit", styles)

    def test_model_library_reuses_viewer_and_has_device_specific_ar_fallbacks(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('class="button outline library-ios-ar-action" rel="ar"', page)
        self.assertIn("launchAndroidAR(model.glbUrl)", script)
        self.assertIn("no valid USDZ file", script)
        self.assertIn("no valid GLB file", script)
        self.assertIn("Apple Quick Look", script)
        self.assertIn("Android Scene Viewer", script)
        self.assertIn("[...activePreviews.keys()]", script)
        self.assertIn("await loadPreview(modelLibrary", script)
        self.assertIn('button.dataset.previewUnavailable === "true"', script)


if __name__ == "__main__":
    unittest.main()
