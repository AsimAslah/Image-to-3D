# TripoSR Application Repository

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-Required-ee4c2c.svg)](https://pytorch.org/)
[![Gradio](https://img.shields.io/badge/Gradio-4.20.1-orange.svg)](https://www.gradio.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Based on TripoSR](https://img.shields.io/badge/Based%20on-TripoSR-7c3aed.svg)](https://github.com/VAST-AI-Research/TripoSR)

> A cleaned and application-ready repository based on the open-source TripoSR project for fast single-image 3D reconstruction.

## 📌 Table of Contents

- [Project Overview](#-project-overview)
- [Features](#-features)
- [Technologies Used](#-technologies-used)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Usage](#-usage)
- [Project Structure](#-project-structure)
- [How the Application Works](#-how-the-application-works)
- [Screenshots](#-screenshots)
- [Future Improvements](#-future-improvements)
- [Known Limitations](#-known-limitations)
- [License](#-license)
- [Contact](#-contact)

## 🚀 Project Overview

This repository is based on the open-source [TripoSR](https://github.com/VAST-AI-Research/TripoSR) project, a feed-forward 3D reconstruction system that generates 3D assets from a single input image.

The original TripoSR model and research were developed by Tripo AI and Stability AI. This repository does not claim ownership of the original model, training process, research, or pretrained weights. Instead, it provides a cleaned project structure with customizations and application-level modifications intended to make the project easier to run, document, and maintain as a GitHub repository.

Use this project to experiment with image-to-3D reconstruction through either a command-line workflow or a local Gradio interface.

## ✨ Features

- 🖼️ Single-image 3D reconstruction
- 🧹 Optional automatic background removal with `rembg`
- 🎛️ Adjustable foreground scaling and marching-cubes resolution
- 📦 OBJ and GLB mesh export support
- 🎨 Optional texture baking workflow
- 🎥 Optional rendered preview video generation from the CLI
- 🌐 Local Gradio web application for interactive usage
- 📁 Example input images included for quick testing

## 🧰 Technologies Used

- Python
- PyTorch
- Transformers
- Hugging Face Hub
- Gradio
- rembg
- trimesh
- xatlas
- torchmcubes
- Pillow
- NumPy
- imageio

## ✅ Requirements

- Python 3.8 or newer
- Git
- A working PyTorch installation
- CUDA-compatible NVIDIA GPU recommended for practical performance
- CPU execution is supported as a fallback, but it is significantly slower
- Sufficient disk space for dependencies, cached pretrained weights, and generated 3D outputs

> Important: install PyTorch using the command recommended for your operating system, Python version, and CUDA version from the official [PyTorch installation guide](https://pytorch.org/get-started/locally/).

## ⚙️ Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/your-username/your-repository-name.git
   cd your-repository-name
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   Windows:

   ```bash
   .venv\Scripts\activate
   ```

   macOS/Linux:

   ```bash
   source .venv/bin/activate
   ```

3. Upgrade packaging tools:

   ```bash
   pip install --upgrade pip setuptools wheel
   ```

4. Install PyTorch for your platform from the official PyTorch instructions.

5. Install project dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## ▶️ Usage

### Command-Line Inference

Generate a 3D mesh from a sample image:

```bash
python run.py examples/chair.png --output-dir output/
```

Export as GLB:

```bash
python run.py examples/chair.png --model-save-format glb --output-dir output/
```

Generate a mesh with baked texture:

```bash
python run.py examples/chair.png --bake-texture --texture-resolution 2048 --output-dir output/
```

Render preview frames and a video:

```bash
python run.py examples/chair.png --render --output-dir output/
```

Show all CLI options:

```bash
python run.py --help
```

### Local Gradio Application

Start the web interface:

```bash
python gradio_app.py
```

Run on a custom port:

```bash
python gradio_app.py --port 7860
```

Allow access from other devices on the network:

```bash
python gradio_app.py --listen
```

Enable basic authentication:

```bash
python gradio_app.py --username admin --password your-password
```

## 📁 Project Structure

```text
.
├── examples/                 # Sample input images
├── figures/                  # Project images and visual references
├── tsr/                      # TripoSR model and rendering source code
│   ├── models/               # Network, tokenizer, renderer, and transformer modules
│   ├── bake_texture.py       # Texture baking utilities
│   ├── system.py             # Main TSR model system wrapper
│   └── utils.py              # Image processing and helper utilities
├── gradio_app.py             # Interactive local web UI
├── run.py                    # Command-line inference script
├── requirements.txt          # Python dependencies
├── LICENSE                   # MIT license from the original project
└── README.md                 # Project documentation
```

## 🧠 How the Application Works

1. The user provides one or more input images.
2. The application optionally removes the image background and resizes the foreground object.
3. The pretrained TripoSR model is loaded from Hugging Face or a local model path.
4. The model predicts a compact 3D scene representation from the processed image.
5. A mesh is extracted using marching cubes.
6. The result is exported as an OBJ or GLB file.
7. Optional steps can bake a texture atlas or render preview frames/video.

The Gradio app wraps this workflow in a browser-based interface, while `run.py` exposes the same core pipeline for scripted or batch usage.

## 🖼️ Screenshots

> Placeholder section for future screenshots.

Suggested screenshots:

- Gradio upload screen
- Processed foreground preview
- Generated OBJ/GLB model preview
- Example output from `examples/chair.png`

## 🛣️ Future Improvements

- Add automated smoke tests for CLI argument parsing and preprocessing
- Add a Dockerfile for reproducible GPU deployment
- Add example output screenshots and generated mesh previews
- Add optional configuration files for model path, device, and output settings
- Improve error messages for missing CUDA, missing weights, or dependency installation issues
- Add CI checks for formatting and dependency validation

## ⚠️ Known Limitations

- Output quality depends heavily on input image framing, object visibility, and background quality.
- High marching-cubes resolutions and texture baking can require substantial VRAM.
- CPU execution is supported but may be slow.
- The first run may download pretrained model assets from Hugging Face.
- `torchmcubes` installation can be sensitive to CUDA and PyTorch version compatibility.
- This repository depends on the original open-source TripoSR implementation and pretrained model availability.

## 📄 License

This repository retains the MIT license included with the original TripoSR project. See [LICENSE](LICENSE) for details.

Please review the original TripoSR repository, model card, and related research materials for any additional usage guidance around the pretrained model and research artifacts.

## 📬 Contact

For questions about this customized application repository, open an issue in this GitHub repository or update this section with your preferred maintainer contact details.

For the original TripoSR research and model, refer to the official [VAST-AI-Research/TripoSR](https://github.com/VAST-AI-Research/TripoSR) project.
