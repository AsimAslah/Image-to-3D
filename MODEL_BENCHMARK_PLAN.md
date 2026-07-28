# Furniture Image-to-3D Model Benchmark Plan

## Purpose and scope

This is a future-production R&D benchmark for furniture reconstruction from one image. It does not replace, import, or modify the working TripoSR production path. It also does not change the Supabase schema.

The benchmark asks a narrower question than a visual demo: which candidate most consistently produces complete furniture geometry, preserves thin parts and source appearance, exports a self-contained PBR GLB, works in Android AR, and remains suitable for conversion to a textured USDZ for Apple Quick Look?

The executable artifact is [`furniture_image_to_3d_benchmark.ipynb`](furniture_image_to_3d_benchmark.ipynb). It is designed for Google Colab Linux with an NVIDIA GPU. Model repositories and weights are revision-pinned in the notebook.

## Existing application findings

The current application already separates model generation from delivery and storage:

- `web-Brickrat/main.py` serializes conversions, creates `generated/<conversion_id>/`, invokes `triposr_service.py`, and exposes GLB/USDZ only when their validation reports pass.
- `triposr_service.py` preserves a source UV/base-colour texture when one exists, otherwise bakes TripoSR vertex colours into a texture atlas, and finally uses an image-derived fallback colour only when neither is available. The GLB material uses explicit roughness and metallic values.
- OBJ is exported with an MTL and texture resources. GLB must contain a mesh, UVs, a PBR material, an embedded base-colour texture, and no external buffer. USDZ is offered only after package validation.
- Android uses the validated HTTPS GLB in Scene Viewer. iPhone/iPad uses only a validated USDZ through a direct `rel="ar"` Quick Look link. The PWA service worker deliberately avoids caching generated model routes.
- Supabase Storage receives `models/<conversion_id>/model.obj`, `model.glb`, and optional `model.usdz`. The product row stores public URLs. Source images are deduplicated by SHA-256, and failed saves clean up newly uploaded objects.

A future provider should therefore return a validated, portable asset bundle to the existing export/storage boundary; it should not bypass the current AR or Supabase safeguards.

## Verified candidate requirements

Requirements below are from official repositories, papers, model cards, and weight listings as checked on 2026-07-15. “Approximate time” is a published model/inference figure where the authors provide one; the notebook measures end-to-end wall time including model loading and export separately.

| Model | Licence and commercial restrictions | Hardware, OS, CUDA, Python | Model size | Geometry, texture, output and PBR | Published approximate time | Colab T4 / L4 / A100 |
|---|---|---|---|---|---|---|
| Microsoft TRELLIS.2-4B | MIT for model/code. Audit separately licensed dependencies such as `nvdiffrast` and `nvdiffrec`. Commercial use is permitted by MIT subject to those dependency terms. | Linux only tested; NVIDIA GPU with **at least 24 GB memory**; verified by authors on A100/H100; CUDA toolkit 12.4 recommended; Python >=3.8. Official setup defaults to Python 3.10, PyTorch 2.6.0 cu124. | 4B parameters; Hugging Face repository about 16.2 GB. | Arbitrary/open/non-manifold topology; high-resolution mesh; official GLB export. Full PBR attributes include base colour, roughness, metallic and opacity. Official example exports an opaque GLB with alpha retained in the texture. | H100: about 3 s at 512³, 17 s at 1024³, 60 s at 1536³. | T4: no. L4: unsafe because nominal 24 GB normally leaves less than 24 GiB currently free/usable. A100 40/80 GB: yes. |
| Tencent Hunyuan3D 2.1 | Tencent Hunyuan 3D 2.1 Community Licence. It excludes use in the EU, UK and South Korea; includes AUP, distribution/notice, provider disclosure and non-affiliation requirements; and requires a separate licence in the licence's stated >1M-MAU case. Legal review is mandatory before production. Tencent claims no rights in generated outputs, subject to compliance. | Repository claims macOS, Windows and Linux; official test stack is A100, Python 3.10, PyTorch 2.5.1 cu124. CUDA extensions are compiled for the paint path. Official memory figures: 10 GB shape, 21 GB texture, 29 GB shape+texture total. | 3.3B shape + 2B paint; Hugging Face repository about 14.9 GB. | High-resolution shape plus PBR texture synthesis. Official code exports the generated mesh as GLB; a Trimesh object can also be saved as OBJ, although OBJ/MTL loses much of glTF PBR. | No reliable end-to-end time is published by the official repository/model card; record measured notebook time instead of inventing a value. | T4: no full PBR. L4: no full official 29 GB pipeline. A100 40/80 GB: yes. |
| Stability AI Stable Fast 3D | Gated weight access. Stability AI Community Licence: research/non-commercial use and commercial use at or below US$1M annual revenue are free; commercial use above the threshold requires an Enterprise Licence. Accept the licence before downloading. | Python >=3.8; CUDA or MPS optional; CPU fallback; Linux, experimental Windows and experimental Apple MPS. PyTorch must match the platform. Official default uses about 6 GB VRAM. | About 1.006B parameters; weights about 4.02 GB. | UV-unwrapped, textured, relatively low-polygon GLB; delighting; predicted roughness and metallic material parameters. Official CLI exports GLB. OBJ conversion is best-effort. | Model card: under one second for model reconstruction; notebook wall time will be longer because it includes loading, preprocessing and export. | T4: yes. L4: yes. A100: yes. |
| Stability AI SPAR3D (optional newer candidate) | Gated weight access and the same Stability AI Community Licence/US$1M threshold. | Python >=3.8 (repository notes >3.9 depending on PyTorch); CUDA or MPS optional; Linux, experimental Windows and experimental Apple MPS. About 10.5 GB VRAM normally or about 7 GB in low-VRAM mode. | About 2.026B parameters; weights about 7.33 GB. | Point-cloud-conditioned backside reconstruction, UV-unwrapped textured GLB, delighting, roughness and metallic parameters. Official CLI exports GLB. | Model card: under one second for model reconstruction. | T4: yes, especially low-VRAM mode. L4: yes. A100: yes. Manual-only in this benchmark so it does not alter the requested fallback. |

Primary sources:

- [TRELLIS.2 official repository](https://github.com/microsoft/TRELLIS.2), [model card and requirements](https://huggingface.co/microsoft/TRELLIS.2-4B), and [paper](https://arxiv.org/abs/2512.14692)
- [Hunyuan3D 2.1 official repository](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1), [licence](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE), [model card](https://huggingface.co/tencent/Hunyuan3D-2.1), and [paper](https://arxiv.org/abs/2506.15442)
- [Stable Fast 3D official repository](https://github.com/Stability-AI/stable-fast-3d), [model card](https://huggingface.co/stabilityai/stable-fast-3d), and [paper](https://arxiv.org/abs/2408.00653)
- [SPAR3D official repository](https://github.com/Stability-AI/stable-point-aware-3d), [model card](https://huggingface.co/stabilityai/stable-point-aware-3d), and [paper](https://arxiv.org/abs/2501.04689)
- [NVIDIA CUDA minor-version compatibility table](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)

The notebook installs CUDA 12.4 PyTorch wheels, so its preflight requires a Linux NVIDIA driver of at least 525.60.13. TRELLIS.2 and Hunyuan also require an nvcc 12.4 toolkit for their pinned compiled extensions. Hunyuan's additional `facebook/dinov2-giant` encoder and the `facebook/dinov2-large` encoder required by SF3D/SPAR3D are pinned and downloaded into local snapshot directories before offline inference. For SF3D/SPAR3D, the copied model configuration is redirected to that pinned local encoder path.

Licence summaries are engineering notes, not legal advice. Review the complete current licence and all dependencies before commercial deployment.

## Recommended test order and fallback

Use the following order for an initial resource-aware run:

1. Run TRELLIS.2 only on Linux when `nvidia-smi` reports at least 24 GiB currently free, `nvcc` is present, and at least about 42 GiB disk is free. Prefer an A100. Start at the official default 512³ path.
2. Test Hunyuan3D 2.1 separately on an A100 with at least 29 GiB currently free. It is not a safe full-PBR choice for T4 or L4. This separate run is important because its PBR paint pipeline targets production materials differently from TRELLIS.
3. Use Stable Fast 3D as the dependable T4/L4 fallback and baseline. Its gated Hugging Face access must already be approved.
4. Optionally test SPAR3D manually on T4/L4/A100 to assess whether point-cloud conditioning improves unseen/backside furniture geometry. It does not replace the mandated automatic fallback.

The notebook's `auto` selector implements TRELLIS.2 -> Hunyuan3D 2.1 when its full selected pipeline fits -> Stable Fast 3D. It reports every rejected model and the exact reason. It never silently runs TripoSR.

## Exact Colab run instructions

1. Upload `furniture_image_to_3d_benchmark.ipynb` to [Google Colab](https://colab.research.google.com/).
2. Select **Runtime > Change runtime type > GPU**. For TRELLIS.2 or full Hunyuan3D 2.1, choose an A100 when the account offers it. GPU allocation is not guaranteed on free Colab.
3. Run **Section 1 only**. Confirm Linux, NVIDIA GPU name, driver, CUDA/nvcc, currently free VRAM, system RAM, and disk. Do not proceed if the selector later reports `BLOCKED`.
4. In Section 2 set `MOUNT_DRIVE=True` if results must survive a runtime reset. The default persistent directory is `MyDrive/furniture_image_to_3d_benchmark`.
5. The saved notebook currently uses `MODEL_CHOICE='spar3d'` with `SPAR3D_LOW_VRAM=True` for a T4-class runtime. Set `MODEL_CHOICE='auto'` only for the fallback test, or explicitly select another model in a separate compatible runtime.
6. Run model selection. Read the printed selection log and reason before installation.
7. Run dependency installation. It creates an isolated Python 3.10 environment and a pinned detached repository checkout. If compilation fails, stop and inspect `logs/install_<model>.log`; do not run inference with a partial install.
8. Run model download. For SF3D/SPAR3D, accept the licence on the official Hugging Face page first and enter a read-only token at the hidden prompt. Never paste a token into a source cell.
9. Upload these five consistently named files (PNG/JPEG/WebP):
   - `chair_thin_legs.*`
   - `sofa.*`
   - `table.*`
   - `metallic_furniture.*`
   - `textured_fabric_or_wood.*`
10. Run preprocessing. The manifest records source and processed SHA-256 values. With Drive mounted, use the same manifest and set `UPLOAD_NEW_IMAGES=False` in later model runtimes.
11. Run inference. A separate raw work directory is created for each input. Any OOM or model failure stops without falling back to another model.
12. Run textured-GLB export normalization, validation, the optional OBJ export, inspect `preview.png`, and use the interactive GLB preview.
13. Edit `human_scores.json` with 1–5 scores after comparing each source and output. Re-run the comparison cell.
14. Download the selected model's ZIP. On the next fresh runtime, repeat from step 2 with a different explicit model and the same Drive-backed inputs.

Colab may reclaim a runtime during long installation or Hunyuan texturing. Drive persists benchmark data, but model environments and caches intentionally remain on ephemeral `/content` and must be rebuilt after a reset.

## Reproducible comparison method

Every compatible model receives the same preprocessed 512×512 PNG and source-image hash. The notebook records and applies seed 42 to model subprocesses; CUDA kernels can still have small platform-dependent nondeterminism. Run one image at a time to release CUDA memory after failure. Store results under:

```text
outputs/<model_name>/<input_name>/
  model.glb
  model.obj                 # when a faithful-enough single-mesh export is supported
  model.mtl                 # when produced
  textures/                 # OBJ texture resources when produced
  preview.png
  validation_report.json
  runtime_metrics.json
  inference.log
```

`runtime_metrics.json` records model/repository/weight revisions, GPU, wall time, GPU-memory samples, model-reported PyTorch peak where available, input hashes, and GLB size.

`validation_report.json` records:

- file existence and non-zero size;
- GLB 2.0 header/chunk validity and Trimesh loading validity;
- vertex and triangle/polygon counts;
- number of connected components;
- per-geometry and aggregate watertightness;
- winding consistency, non-finite vertices, invalid face indices, and degenerate faces;
- embedded versus external textures, external buffer URIs, and image MIME types;
- material names, base-colour factor/texture, roughness, metallic, metallic-roughness texture, normal, occlusion, emissive and alpha fields;
- explicit validation errors/warnings plus technical Android GLB and iPhone USDZ-conversion candidate flags.

Best-effort OBJ conversion writes `obj_export_report.json` and also adds its result to `validation_report.json`; unsupported multi-geometry conversion is reported rather than silently flattening materials.

The candidate flags are heuristics, not device certification. Test shortlisted assets on actual Android Scene Viewer and Apple Quick Look after conversion through the existing validated USDZ pipeline.

Human reviewers score geometry completeness, thin-part preservation, texture accuracy, and colour preservation from 1–5. They should rotate the model, inspect the rear/underside, compare material response under neutral and bright lighting, and note whether disconnected components are intentional furniture parts or reconstruction failures.

## Known single-image limitations

- The back, underside, inside of cushions, and occluded joints are not observed; every model must hallucinate them.
- Symmetry priors can invent or delete legs, armrests, shelves, crossbars and hardware.
- Thin legs, wires, slats and transparent surfaces occupy few pixels and are easily merged, broken or removed during background segmentation, reconstruction, remeshing or decimation.
- Perspective and unknown camera intrinsics make scale, depth and parallel edges ambiguous.
- Highlights and shadows can be baked into base colour. Delight/relighting methods reduce but do not eliminate this problem.
- A single image cannot reliably distinguish painted metal, glossy plastic, varnished wood and specular fabric. Metallic/roughness maps therefore require review.
- Logos, wood grain, patterned fabric and repeated texture may be mirrored, stretched or fabricated on unseen surfaces.
- Watertightness is not automatically a quality signal for AR: open surfaces can be intentional, while a watertight mesh can still contain incorrect filled gaps.
- High polygon count, texture resolution and physical material richness improve fidelity but increase GLB size, mobile memory use, download time and USDZ conversion risk.

For the strongest future result, consider requesting multiple guided views or a short turntable video after this single-image benchmark establishes the best baseline.

## Future FastAPI/cloud integration (not implemented)

A production version should treat GPU reconstruction as an asynchronous provider, not run a large model inside the current FastAPI web process.

1. FastAPI accepts and validates an image, stores the source in a private staging location, and creates a provider job with an idempotency key.
2. A cloud GPU worker selects a configured model/version, downloads the source, runs preprocessing/inference/export/validation, and writes a structured result bundle.
3. FastAPI polls the provider or receives a signed callback. User-visible states should be `queued`, `provisioning`, `running_shape`, `running_texture`, `validating`, `uploading`, `succeeded`, `failed`, or `cancelled`.
4. Only after GLB validation succeeds should the current USDZ exporter/converter run. Quick Look availability remains conditional on USDZ validation.
5. The final GLB, OBJ bundle, USDZ, preview, validation report and runtime metrics are uploaded to Supabase Storage using server-side credentials. Public or signed URLs are written through the existing save boundary.
6. The current product page polls a status endpoint with exponential backoff and can resume after a PWA reload. Cancellation should be best-effort and uploads should be idempotent.
7. Temporary cloud files, failed uploads and orphaned jobs need retention policies and periodic cleanup.

No Supabase schema is changed in this experiment. A later integration design may need durable job-state storage, but that requires a separately reviewed migration rather than overloading the current product row. The repository ignore rules cover the notebook's `/.benchmark_runtime/` local fallback so temporary weights, caches and outputs cannot be added accidentally.

## Estimated integration risks

| Risk | Impact | Mitigation before production |
|---|---|---|
| GPU capacity and cold starts | Long/variable checkout time and cost | Queue jobs, maintain warm workers for paid traffic, set per-stage deadlines, expose honest status |
| CUDA/custom-extension fragility | Install or runtime failure after base-image updates | Build immutable tested Linux CUDA images; pin repository, weights, PyTorch and compiler toolchain |
| OOM on large PBR pipelines | Failed jobs and wasted GPU time | Preflight free VRAM/disk, one job per GPU, stage/unload models, cap texture/mesh resolution, never silent-fallback |
| Licence restrictions | Production launch may be prohibited or require enterprise terms/disclosures | Legal review per model and dependency; record model/version/licence with each generated asset |
| Hidden geometry and material hallucination | Incorrect marketplace assets and poor AR trust | Human QA, confidence/status labels, multi-view capture option, reject incomplete meshes |
| Mobile GLB size/polycount | Slow downloads, browser crashes, poor Scene Viewer performance | Create validated mobile LODs, texture compression policy, device performance budget and real-device tests |
| USDZ material conversion | White/missing materials in Quick Look | Keep embedded portable textures, preserve PBR maps, run the existing package validator, test real iPhones |
| Coordinate/scale mismatch | Furniture floats, clips, or appears at the wrong real-world size | Normalize axes/origin, request or infer dimensions, store explicit metric scale, add floor-placement tests |
| Supabase partial failure | Orphaned objects or broken product rows | Idempotent paths, upload-then-commit, rollback/cleanup, checksum verification and retry policy |
| Security/privacy | Leaked source images, tokens or model URLs | Private staging, short-lived signed URLs, server-side secrets, log redaction, retention/deletion controls |

## Executed versus expected results

At repository implementation time, only the local repository inspection and notebook static validation were executed. No candidate model was installed, no weights were downloaded, and no GPU inference or AR device test was performed on this Windows AMD development computer.

Consequently:

- the requirement/licence/size/timing table is sourced from official published material;
- notebook-generated VRAM, timing, geometry, texture, PBR and file-size fields are **not yet measured**;
- all geometry completeness, thin-part, texture and colour scores remain **not scored** until real outputs are reviewed;
- a production recommendation must wait for completed A100 and T4/L4 runs plus Android and iPhone device validation.

The initial expected ranking is a hypothesis, not a result: TRELLIS.2 is the quality-first A100 candidate, Hunyuan3D 2.1 is the A100 PBR-material specialist with significant licence constraints, SF3D is the practical T4/L4 baseline/fallback, and SPAR3D is the optional lower-memory test for improved unseen/backside geometry.
