# web-Brickrat

FastAPI product studio for turning furniture images into TripoSR OBJ/GLB models
and saving product metadata and asset links to Supabase.

## Run

```powershell
cd C:\Git\TripoSR\web-Brickrat
pip install -r requirements.txt
Copy-Item .env.example .env
# Fill in the Supabase values in .env
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`. Before saving a product, run `supabase.sql` in
the Supabase SQL editor and create a public Storage bucket named `products`.

The application uses the TripoSR source in the parent `C:\Git\TripoSR`
directory. Model weights load on the first conversion request.

The product form accepts a Supabase table name (for example, `products` or
`chairs`). Every selected table must already exist with the columns defined in
`supabase.sql`. Table names are validated before use. While conversion or save
requests are running, their controls are locked to prevent duplicate requests.
The success notification includes an Undo action that deletes the inserted row
and makes a best-effort cleanup of its uploaded assets.

Image files are content-addressed with SHA-256. Saving a conversion whose image
already exists reuses the stored image URL and updates that product row instead
of uploading or inserting a duplicate. Existing custom tables need an
`image_sha256 text` column with a unique partial index equivalent to the one in
`supabase.sql`.

The result view renders OBJ and GLB separately and shows the processed model
input beside the source image. The furniture quality preset uses detail-aware
background matting, resolution 320, and a density threshold of 20 to retain
weaker thin geometry. Single-image reconstruction still cannot guarantee
geometry that is fully hidden or ambiguous in the source photograph.

## AR preview

After conversion, the result view uses `<model-viewer>` to load the generated
`model.glb` from the app's `/generated/<conversion_id>/model.glb` static route.
The GLB preview supports desktop/browser viewing with camera controls and
auto-rotation. Android AR uses the GLB through model-viewer WebXR or Scene
Viewer. OBJ remains available for preview and download, but AR uses GLB on
Android.

iPhone Safari AR requires USDZ through Apple Quick Look. If a `model.usdz` file
exists beside `model.glb` in the generated conversion folder, the template adds
`ios-src` and the Supabase save flow uploads `usdz_url`. TripoSR does not
generate USDZ in this app yet, so USDZ is optional placeholder support for a
future converter or a manually supplied file.

WebXR and mobile AR require HTTPS on deployed sites. Localhost is acceptable for
desktop development. For mobile testing, use ngrok or deploy behind HTTPS
hosting.

Testing checklist:

1. Run `uvicorn main:app --reload`.
2. Open `http://127.0.0.1:8000`.
3. Upload a furniture image and convert it.
4. Confirm `model.obj` and `model.glb` are generated.
5. Confirm the OBJ preview, GLB preview, and both download links appear.
6. Use an ngrok HTTPS URL or deployed HTTPS URL for mobile testing.
7. On a supported Android device, tap `View in AR` and confirm GLB AR opens.
8. On iPhone Safari without USDZ, confirm the pending-support message appears.
9. To test iPhone Quick Look, have a future converter or manual test hook place
   `model.usdz` in the generated conversion folder before the result template is
   rendered; then confirm `View in AR` opens Apple Quick Look.
10. Save to Supabase and confirm the existing save/undo flow still works.
