# Furniture 3D AR Studio

FastAPI/PWA frontend for converting a furniture photo with TripoSR, exporting
portable OBJ/GLB assets, optionally converting a validated GLB to USDZ, and
saving the product and public asset URLs to Supabase.

## Real-world dimensions

A single furniture photo does not contain a dependable real-world scale. After
choosing a geometry candidate, the user must enter width, height, and depth and
apply them before Supabase saving or mobile AR is enabled. The supported input
units are centimetres, millimetres, metres, inches, and feet.

The backend reads the untouched selected GLB bounding box with this fixed mapping:

- X = width
- Y = height
- Z = depth

All inputs are converted to metres. **Preserve proportions** uses the largest
uniform scale that fits inside all three entered limits. **Exact dimensions**
uses separate X/Y/Z scale factors and warns that the result can stretch or
squash the source geometry. The UI reports the measured final dimensions and
the applied factors.

The original generated candidate is never overwritten. Each update rebuilds a
new `generated/<conversion-id>/dimensioned/` bundle from that original, so
repeated edits cannot accumulate scale. GLB, OBJ, and USDZ are all re-exported;
GLB and USDZ are Y-up and authored in metres. The USDZ world bounds are compared
to the GLB bounds before Quick Look is enabled. Reset removes only this derived
bundle and returns the conversion to its original unitless scale.

Run `supabase.sql` before saving dimensioned models. In addition to the original
product columns, it stores the entered values and unit, metre values, scaling
mode, X/Y/Z factors, axis/orientation metadata, measured final dimensions, and
optional room/fit results.

## What the export contains

TripoSR in this repository returns geometry plus per-vertex colours. It does not
produce an original photograph UV texture. The export pipeline now distinguishes
three truthful material cases:

1. Preserve an existing source UV/base-colour texture when one is available.
2. Bake TripoSR vertex colours into an embedded texture atlas. This keeps colour
   visible in GLB and gives Quick Look a supported UV texture instead of relying
   on unsupported vertex-colour rendering.
3. If neither exists, derive a dominant colour from the uploaded object and mark
   the result as a fallback in `material_report.json` and in the UI.

The GLB is rejected unless it contains a mesh, UVs, a PBR material, a base-colour
texture, and an embedded image. OBJ is exported with its MTL and texture files.
USDZ is offered only when conversion succeeds and the package contains both a
USD scene and texture image.

## Install and run

The requirements include Pixar OpenUSD's `usd-core` wheel so USDZ generation
works on Windows, Linux, and macOS without a separately installed converter.

```powershell
cd C:\Git\TripoSR\web-Brickrat
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# Install the PyTorch build matching your CPU/CUDA platform first:
# https://pytorch.org/get-started/locally/
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Fill in SUPABASE_URL, SUPABASE_KEY, SUPABASE_STORAGE_BUCKET, and
# SUPABASE_PRODUCTS_TABLE in .env.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://127.0.0.1:8000`. Mobile AR requires the deployed app and model
URLs to use HTTPS. Run `supabase.sql` in Supabase and create a public Storage
bucket named `products` before saving.

The web server and export/unit tests can start without PyTorch. The first real
TripoSR conversion loads PyTorch, rembg, and the model lazily and reports a
clear installation error if the ML runtime is missing.

## Conversion speed and progress

The normal conversion path now uses the faster single-model settings: 256 mesh
resolution, standard background removal, and one geometry threshold. The
three-variant quality comparison remains available as an explicit option and
uses 320 resolution plus detail-preserving background removal, but performs
roughly three times the geometry/export work.

JavaScript clients upload to `POST /api/conversions` and poll the returned
same-origin status URL. The interface shows upload progress, backend conversion
stages, a monotonic percentage, and elapsed time. Completed HTML is loaded from
the returned result URL without regenerating the model. The existing synchronous
`POST /convert` route remains as the no-JavaScript and backward-compatible
fallback. Conversion jobs are process-local, so run a single Uvicorn worker;
`--reload` is appropriate for local development.

## Saved model library

The home page loads existing rows from the same Supabase products table through
`GET /api/models`. `SUPABASE_PRODUCTS_TABLE` selects the server-side table and
defaults to `products`; a table name is never accepted from this public API.
The endpoint returns only sanitized display metadata and validated HTTP(S)
asset URLs. Supabase credentials remain on the FastAPI server.

Saved cards support name search and show a category filter only when returned
rows contain categories. GLB files open in the shared on-demand viewer, Android
uses the HTTPS GLB with Scene Viewer, and iPhone/iPad uses the HTTPS USDZ with
Apple Quick Look. Records with missing optional metadata or formats remain
visible with explicit unavailable states.

`numpy>=1.24,<2` is pinned because the installed Trimesh 4.0.5 release uses
NumPy APIs removed in NumPy 2.

## USDZ generation

The backend authors a binary USD scene from the textured Trimesh mesh and uses
OpenUSD's package writer to create the uncompressed, 64-byte-aligned USDZ that
Apple Quick Look requires. The exporter includes the UV texture, PBR material,
normals, metric scale, Y-up orientation, and floor placement. The resulting
package is rejected unless its USD scene, texture, ZIP storage, and alignment
all validate.

An existing compatible converter can still be selected as an optional override:

```powershell
$env:USDZ_CONVERTER = "C:\Tools\usd_from_gltf.exe"
& $env:USDZ_CONVERTER --help
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

If the optional converter fails validation, the app automatically falls back to
its OpenUSD exporter. A failed USDZ export does not invalidate the GLB or OBJ.

## Mobile previews, AR, and PWA behaviour

The conversion result initially renders only the product image, validation
status, file sizes, and actions. GLB, OBJ, `<model-viewer>`, and Three.js are
loaded only after the corresponding preview button is pressed. Downloads show
measured transferred bytes, mobile files over 10 MB show a warning, and files
over 25 MB require confirmation. Closing a preview aborts its request, revokes
blob URLs, stops render loops, and disposes WebGL resources. Opening the other
preview unloads the active one first.

- Android opens the validated public HTTPS GLB in Scene Viewer and falls back to
  the unchanged product page when Scene Viewer is unavailable.
- iPhone/iPad uses a direct `rel="ar"` Apple Quick Look link to a validated USDZ.
  A GLB is never presented as an iPhone AR file.
- Desktop shows on-demand WebGL previews without misleading mobile AR controls.

AR actions remain locked until real dimensions have been applied to the exported
files. Resizing only the browser preview is never treated as a dimensional
update.

Preview assets use explicit inline routes and model MIME types; download routes
use attachments. Both support byte ranges and `no-store` cache headers. Public
asset URLs are built from the current or forwarded host/protocol, so an HTTPS
ngrok page does not embed localhost or mixed-content model URLs.

`manifest.json` includes 192 px, 512 px, and maskable icons. The PWA uses a
standalone display, root start URL/scope, a registered service worker, hashed
asset and cache versions, cache-first stable static assets, network-first HTML
navigation with a dedicated offline fallback, old-cache deletion, and network-only
generated/model routes. The service worker checks for updates after page load and
does not intercept Apple Quick Look or substitute a cached GLB, OBJ, or USDZ.

## Room measurement, fit checks, and platform limits

Manual room width, length, height, unit, and optional placement-area width/depth
work on desktop, Android, iPhone, and installed PWA mode. Fit checking evaluates
both width x depth and depth x width orientations and reports:

- Fits in room
- Does not fit
- Fits only after rotation
- Width, depth, and height clearance (negative values are shortages)

The optional WebXR measurement button is hidden unless a secure browser first
confirms `immersive-ar`. Starting a session additionally requires the WebXR
`hit-test` feature. The user aims the centre reticle at detected real-world
surfaces, marks two points for a distance or three/four successive floor
corners, and then reviews or corrects the resulting ordinary form values.
Support is browser/device dependent; manual entry is always the fallback.

Apple RoomPlan is a native Swift framework powered by ARKit, camera input, and a
LiDAR Scanner. It is not exposed to normal Safari pages or installed web PWAs,
so this project does not claim that RoomPlan works in Safari. iPhone/iPad web AR
continues to use a direct USDZ Quick Look link for model placement, not room
scanning. Relevant primary documentation:

- [Apple RoomPlan](https://developer.apple.com/documentation/roomplan)
- [RoomPlan device support](https://developer.apple.com/documentation/RoomPlan/RoomCaptureSession/isSupported)
- [AR Quick Look from a web page](https://developer.apple.com/documentation/ARKit/previewing-a-model-with-ar-quick-look)
- [WebXR Hit Test specification](https://www.w3.org/TR/webxr-hit-test-1/)

For a future native iOS companion or App Clip, `room_capture.py` defines a
versioned `apple_roomplan` payload containing metric room dimensions, floor
plane, wall positions/normals/dimensions, and door/window/opening data.
`POST /api/room-captures/validate` validates and normalizes that contract but
deliberately does not retain privacy-sensitive scans. A production companion
should add user authentication, consent, encrypted storage or a short-lived
handoff token, and then populate the same editable room fields used by the PWA.

## Diagnostics and tests

Inspect generated content without loading the ML model:

```powershell
python model_diagnostics.py generated\<conversion-id>\model.glb `
  --usdz generated\<conversion-id>\model.usdz
```

Or temporarily enable the developer endpoint (never enable it publicly):

```powershell
$env:MODEL_DEBUG = "true"
# GET /debug/models/<conversion-id>
```

Run tests and syntax checks:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
node --check static\dimensions.js
node --check static\app.js
```

The suite covers unit conversion, positive/finite validation, uniform and
per-axis scale factors, explicit axis mapping, non-accumulating GLB rebuilds,
room conversion, placement-area overrides, both furniture orientations, and all
fit outcomes.

The application logs UV presence, vertex-colour presence, material strategy,
texture filenames/sizes, embedded GLB images, USDZ package textures, export file
sizes, converter selection, Supabase upload results, final public URLs, and
frontend device/AR-mode detection. Secrets and environment values are not logged.

Unexpected server errors receive a short reference in both the HTML response and
the `X-Error-Reference` response header. The complete traceback is retained in
`server.log`, which rotates at 5 MB and keeps three backups, so restarting the
server does not erase the cause. Set `APP_LOG_PATH` to use a different location.
If conversion finished before result rendering failed, the error response offers
**Recover completed conversion** and the same result can be reopened later at
`/conversions/<conversion-id>`.

## Manual device checklist

1. Convert white, dark, and multi-coloured furniture samples. Confirm the GLB
   preview matches the available TripoSR colour and the UI states whether a
   source texture, vertex-colour atlas, or fallback was used.
2. Download the GLB on another device and confirm it works without OBJ/MTL files.
3. On Android Chrome over HTTPS, tap the single **View in AR** button and test
   WebXR/Scene Viewer, then return to the unchanged product page.
4. On iPhone Safari over HTTPS, confirm the AR button appears only with a valid
   USDZ, opens Quick Look, and returns to the same page when Quick Look closes.
5. Add the site to the iPhone Home Screen and repeat from standalone PWA mode.
6. Confirm each conversion reports a validated USDZ and that the downloaded file
   opens in Apple Quick Look with its texture intact.
7. Simulate a Supabase failure and confirm no database row is created and newly
   uploaded assets are cleaned up.
8. Deploy changed frontend files, reopen an existing installed PWA, and confirm
   the service worker activates the new asset version instead of stale JS/CSS.
9. Apply exact dimensions and verify the displayed final GLB dimensions match.
   Apply a second set and confirm it is based on the original, then reset.
10. On supported Android Chrome over HTTPS, confirm **AR Measure Room** appears,
    mark two points, edit the captured value, and check both fit orientations.
11. On iPhone/iPad Safari, confirm WebXR room controls remain hidden, manual room
    entry works, and Quick Look appears only after dimensioned USDZ export.
