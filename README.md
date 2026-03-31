# 🎙️ Transcribo

**Transcribo** is a lightweight desktop application for fast, offline audio transcription powered by **faster-whisper**. It provides a clean UI built with **pywebview** and supports drag-and-drop batch transcription.

---

## ✨ Features

* ⚡ Fast transcription using **faster-whisper**
* 🖥️ Native desktop app (no browser required)
* 🎯 Drag & drop multiple audio files
* 📦 Automatic model download & caching
* 🧠 Multiple model sizes (tiny → large-v3)
* 💾 Export transcripts as `.txt`
* 📋 Copy-to-clipboard support
* 🎛️ Configurable:

  * Model size
  * Device (CPU / GPU)
  * Compute type (int8 / float16 / float32)

---

## 📁 Supported Formats

* `.wav`
* `.mp3`
* `.m4a`
* `.flac`
* `.ogg`

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/transcribo.git
cd transcribo
```

### 2. Install dependencies

```bash
pip install faster-whisper pywebview
```

---

## ▶️ Running the App

```bash
python transcribo_app.py
```

---

## 🏗️ Build Executable (.exe)

```bash
pip install pyinstaller

pyinstaller --onefile --windowed \
--name Transcribo \
--collect-all faster_whisper \
--collect-all ctranslate2 \
--collect-all webview \
transcribo_app.py
```

The executable will be available in the `dist/` folder.

---

## 🧠 Model Info

* Models are downloaded automatically from Hugging Face on first use.
* Cached locally for future runs.
* Larger models = better accuracy, slower speed.

| Model    | Speed | Accuracy |
| -------- | ----- | -------- |
| tiny     | ⚡⚡⚡⚡⚡ | ⭐        |
| base     | ⚡⚡⚡⚡  | ⭐⭐       |
| small    | ⚡⚡⚡   | ⭐⭐⭐      |
| medium   | ⚡⚡    | ⭐⭐⭐⭐     |
| large-v3 | ⚡     | ⭐⭐⭐⭐⭐    |

---

## 🖥️ UI Overview

* Drag & drop files or click to browse
* Queue system for batch processing
* Live logs & progress tracking
* Expandable transcript viewer
* Export or copy results

---

## ⚙️ Configuration Options

* **Model Size** → Controls speed vs accuracy
* **Compute Type**

  * `int8` → best for CPU
  * `float16` → GPU optimized
  * `float32` → highest precision
* **Device**

  * `cpu`
  * `cuda` (requires NVIDIA GPU)

---

## ⚠️ Notes

* First run may take time due to model download.
* GPU support requires:

  * CUDA installed
  * Compatible NVIDIA GPU
* Windows clipboard uses `clip` command.

---

## 🐞 Troubleshooting

### Model not downloading

* Check internet connection
* Ensure Hugging Face is accessible

### GPU not working

* Install CUDA + cuDNN properly
* Use `device = cuda` and `compute_type = float16`

### App not launching after build

* Try running from terminal to see logs
* Ensure all dependencies were collected in PyInstaller

---

## 📌 Future Improvements

* Subtitle export (`.srt`, `.vtt`)
* Real-time transcription
* Language selection override
* Speaker diarization

---

## 📄 License

MIT License

---

## 🙌 Acknowledgements

* faster-whisper
* pywebview
* Hugging Face
