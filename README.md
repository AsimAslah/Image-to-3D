# Image-to-3D Generation Application

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-Required-ee4c2c.svg)](https://pytorch.org/)
[![Gradio](https://img.shields.io/badge/Gradio-4.20.1-orange.svg)](https://www.gradio.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Built with TripoSR](https://img.shields.io/badge/Built%20with-TripoSR-7c3aed.svg)](https://github.com/VAST-AI-Research/TripoSR)

## Overview

This project is built using TripoSR. This repository contains my implementation and customization of an Image-to-3D Generation Application for academic purposes.

The application converts a single 2D image into a 3D mesh through a command-line workflow or an interactive Gradio interface. It adds application-level integration around the pretrained TripoSR model, including image preprocessing, optional background removal, configurable mesh extraction, OBJ and GLB export, texture baking, and preview rendering.

This repository does not claim ownership of TripoSR, its model architecture, research, pretrained weights, or original source code. TripoSR was developed by [Tripo AI](https://www.tripo3d.ai/) and [Stability AI](https://stability.ai/); the original open-source project is maintained at [VAST-AI-Research/TripoSR](https://github.com/VAST-AI-Research/TripoSR).

## Features

- Generates a 3D mesh from a single input image
- Provides an interactive Gradio web interface
- Supports OBJ and GLB model export
- Removes image backgrounds automatically with `rembg`
- Offers configurable foreground scaling and marching-cubes resolution
- Supports optional texture-atlas baking
- Supports optional rendered preview-video generation from the CLI
- Falls back to CPU execution when CUDA is unavailable

## Technologies Used

- **Language:** Python
- **Machine learning:** PyTorch, Transformers, TripoSR
- **Interface:** Gradio
- **Image processing:** Pillow, NumPy, rembg
- **3D processing:** trimesh, torchmcubes, xatlas, moderngl
- **Model distribution:** Hugging Face Hub
- **Media export:** imageio with FFmpeg support

## System Architecture / Workflow

```text
Input image
    |
    v
Optional background removal and foreground resizing
    |
    v
Pretrained TripoSR model inference
    |
    v
Implicit 3D scene representation
    |
    v
Marching-cubes mesh extraction
    |
    +--> OBJ or GLB export
    +--> Optional texture baking
    +--> Optional rendered preview video
```

The Gradio interface provides this workflow in a browser. `run.py` exposes the same reconstruction pipeline for command-line and batch-oriented use.

## Installation

### Prerequisites

- Python 3.8 or newer
- Git
- A PyTorch installation compatible with the target hardware
- An NVIDIA CUDA-capable GPU is recommended; CPU execution is supported but slower
- Internet access on the first run to download the pretrained model from Hugging Face

### Setup

1. Clone the repository and enter the project directory:

   ```bash
   git clone https://github.com/AsimAslah/TripoSR-Image-to-3D.git
   cd TripoSR-Image-to-3D
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   Windows PowerShell:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   macOS or Linux:

   ```bash
   source .venv/bin/activate
   ```

3. Upgrade the packaging tools:

   ```bash
   python -m pip install --upgrade pip setuptools wheel
   ```

4. Install PyTorch using the command for the operating system and CUDA version from the [official PyTorch installation guide](https://pytorch.org/get-started/locally/).

5. Install the remaining dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Web Application

Start the Gradio interface:

```bash
python gradio_app.py
```

Open `http://127.0.0.1:7860` in a browser, upload an image or select the included chair sample, adjust the options, and select **Generate 3D Model**.

Useful launch options:

```bash
python gradio_app.py --port 7860
python gradio_app.py --listen
python gradio_app.py --share
python gradio_app.py --username admin --password your-password
```

### Command Line

Generate an OBJ mesh from the included sample:

```bash
python run.py examples/chair.png --output-dir output/
```

Export a GLB model:

```bash
python run.py examples/chair.png --model-save-format glb --output-dir output/
```

Generate a textured mesh:

```bash
python run.py examples/chair.png --bake-texture --texture-resolution 2048 --output-dir output/
```

Generate a rendered preview video:

```bash
python run.py examples/chair.png --render --output-dir output/
```

List every CLI option:

```bash
python run.py --help
```

## Project Structure

```text
.
|-- examples/
|   `-- chair.png              # Reproducible sample input
|-- tsr/                       # TripoSR inference and rendering implementation
|   |-- models/                # Model, tokenizer, renderer, and transformer modules
|   |-- bake_texture.py        # Texture-atlas baking utilities
|   |-- system.py              # TripoSR model-system wrapper
|   `-- utils.py               # Image, rendering, and configuration utilities
|-- gradio_app.py              # Interactive web application
|-- run.py                     # Command-line inference entry point
|-- requirements.txt           # Python dependencies
|-- LICENSE                    # Original TripoSR MIT license and copyright
`-- README.md                  # Project documentation
```

The pretrained model configuration and weights are downloaded from the `stabilityai/TripoSR` Hugging Face repository at runtime and are not committed to this repository.

## Output Examples

Generated files are written to the selected output directory and intentionally excluded from version control.

| Workflow | Output |
| --- | --- |
| Default CLI inference | `output/0/mesh.obj` |
| GLB export | `output/0/mesh.glb` |
| Texture baking | Mesh plus `output/0/texture.png` |
| Preview rendering | Render frames plus `output/0/render.mp4` |
| Gradio interface | Downloadable OBJ and GLB models with an interactive preview |

For a reproducible demonstration, use `examples/chair.png` with either the CLI command or the sample selector in the Gradio interface.

## Future Improvements

- Add automated tests for preprocessing, CLI arguments, and output generation
- Add verified screenshots and generated-model previews from project runs
- Add a Docker configuration for reproducible deployment
- Add clearer runtime diagnostics for missing CUDA support or model assets
- Add configurable model, device, and output settings through a project configuration file
- Improve accessibility and progress feedback in the Gradio interface

## Attribution

This application uses the open-source [TripoSR](https://github.com/VAST-AI-Research/TripoSR) implementation and the pretrained [`stabilityai/TripoSR`](https://huggingface.co/stabilityai/TripoSR) model. TripoSR was developed by Tripo AI and Stability AI.

My contribution is the integration, customization, application workflow, and academic implementation presented in this repository. No ownership is claimed over TripoSR, its research, model architecture, pretrained weights, or original source code.

Please consult the original project and model pages for research details, model information, and upstream usage guidance.

## License

The retained TripoSR source code is distributed under the MIT License included in [LICENSE](LICENSE), which preserves the original copyright notice:

> Copyright (c) 2024 Tripo AI & Stability AI

The software is provided without warranty. Review the original [TripoSR repository](https://github.com/VAST-AI-Research/TripoSR), its license, and the associated model documentation before redistribution or deployment.
