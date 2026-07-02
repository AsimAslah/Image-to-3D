# Image-to-3D Generation Application

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-Required-ee4c2c.svg)](https://pytorch.org/)
[![Gradio](https://img.shields.io/badge/Gradio-4.20.1-orange.svg)](https://www.gradio.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Built with TripoSR](https://img.shields.io/badge/Built%20with-TripoSR-7c3aed.svg)](https://github.com/VAST-AI-Research/TripoSR)

## Overview

This project is built using TripoSR. This repository contains my implementation and customization of an Image-to-3D Generation Application for academic purposes.

The application converts a single 2D image into a 3D mesh through an interactive Gradio interface. It adds an application workflow around the pretrained TripoSR model, including image preprocessing, optional background removal, configurable mesh extraction, interactive preview, and OBJ and GLB export.

This repository does not claim ownership of TripoSR, its model architecture, research, pretrained weights, or original source code. TripoSR was developed by [Tripo AI](https://www.tripo3d.ai/) and [Stability AI](https://stability.ai/); the original open-source project is maintained at [VAST-AI-Research/TripoSR](https://github.com/VAST-AI-Research/TripoSR).

## Features

- Generates a 3D mesh from a single input image
- Provides an interactive Gradio web interface
- Supports OBJ and GLB model export
- Removes image backgrounds automatically with `rembg`
- Offers configurable foreground scaling and marching-cubes resolution
- Falls back to CPU execution when CUDA is unavailable

## Technologies Used

- **Language:** Python
- **Machine learning:** PyTorch, Transformers, TripoSR
- **Interface:** Gradio
- **Image processing:** Pillow, NumPy, rembg
- **3D processing:** trimesh, torchmcubes
- **Model distribution:** Hugging Face Hub

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
    v
Interactive 3D preview and OBJ/GLB export
```

The Gradio interface provides the complete application workflow in a browser. The `tsr/` package is the required TripoSR inference engine used by the application; it is retained with its original attribution because the model configuration imports these modules directly.

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
   git clone https://github.com/AsimAslah/Image-to-3D.git
   cd Image-to-3D
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
python app.py
```

Open `http://127.0.0.1:7860` in a browser, upload an image or select the included chair sample, adjust the options, and select **Generate 3D Model**.

Useful launch options:

```bash
python app.py --port 7860
python app.py --listen
python app.py --share
python app.py --username admin --password your-password
```

## Project Structure

```text
.
|-- examples/
|   `-- chair.png              # Reproducible sample input
|-- tsr/                       # TripoSR inference and rendering implementation
|   |-- models/                # Model, tokenizer, renderer, and transformer modules
|   |-- system.py              # TripoSR model-system wrapper
|   `-- utils.py               # Image, rendering, and configuration utilities
|-- app.py                     # Image-to-3D Gradio application
|-- requirements.txt           # Python dependencies
|-- LICENSE                    # Original TripoSR MIT license and copyright
`-- README.md                  # Project documentation
```

The pretrained model configuration and weights are downloaded from the `stabilityai/TripoSR` Hugging Face repository at runtime and are not committed to this repository.

## Output Examples

The Gradio interface displays the generated model in an interactive viewer and provides downloadable OBJ and GLB files. Generated files are temporary runtime artifacts and are intentionally excluded from version control.

For a reproducible demonstration, use `examples/chair.png` through the sample selector in the Gradio interface.

## Future Improvements

- Add automated tests for preprocessing and output generation
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
