# Third-party licenses

Direct dependencies only. Licenses verified from installed package metadata (spec §0 rule 7).
Only MIT, BSD, Apache-2.0, ISC, MPL-2.0, Unlicense, and PSF licenses are allowed.

## Python (`pyproject.toml`)

| Package | Version | License | Milestone |
|-|-|-|-|
| fastapi | 0.143.1 | MIT | M0 |
| uvicorn | 0.54.0 | BSD-3-Clause | M0 |
| httpx | 0.28.1 | BSD-3-Clause | M0 |
| platformdirs | 4.13.0 | MIT | M0 |
| pytest (dev) | 9.1.1 | MIT | M0 |
| pytest-asyncio (dev) | 1.4.0 | Apache-2.0 | M0 |
| ruff (dev) | 0.17.0 | MIT | M0 |
| pypdfium2 | 5.14.0 | BSD-3-Clause OR Apache-2.0 (bundles PDFium: BSD-3-Clause/Apache-2.0 and other permissive third-party licenses) | M1 |
| python-docx | 1.2.0 | MIT (depends on lxml, BSD-3-Clause) | M1 |
| python-multipart | 0.0.32 | Apache-2.0 | M1 |
| sqlite-vec | 0.1.9 | MIT OR Apache-2.0 | M1 |
| reportlab | 5.0.1 | BSD-3-Clause | M3 |
| pillow (required by reportlab) | 12.3.0 | MIT-CMU (the HPND "PIL Software License"; not on the §0 list, approved by the owner on 2026-10-14) | M3 |
| markdown-it-py | 4.2.0 | MIT (depends on mdurl 0.1.2, MIT) | M3 |
| charset-normalizer (required by reportlab) | 3.5.2 | MIT | M3 |
| trafilatura | 2.3.1 | Apache-2.0 | M5 |
| youtube-transcript-api | 1.2.4 | MIT | M5 |
| yt-dlp | 2026.8.19 | Unlicense | M5 |
| faster-whisper | 1.2.1 | MIT | M5 |
| pytesseract | 0.3.13 | Apache-2.0 | M5 |
| playwright (dev) | 1.64.0 | Apache-2.0 (bundles its Node driver, also Apache-2.0) | M7 |
| greenlet (dev, required by playwright) | 3.5.6 | MIT AND PSF-2.0 | M7 |
| pyee (dev, required by playwright) | 14.0.0 | MIT | M7 |
| numpy | 2.5.4 | BSD-3-Clause (wheel also bundles components under 0BSD, MIT, Zlib, CC0-1.0) | M2 |

M6 adds no Python packages: Kokoro ONNX inference uses numpy and onnxruntime (already listed) and
`huggingface-hub` for the model download. The Kokoro model (Apache-2.0) is downloaded by the user at
runtime, not shipped. `espeak-ng` (GPL-3.0) and `ffmpeg` are **separate programs** run as subprocesses
and are never linked or bundled (allowed by §0); users install them themselves.

### Transitive dependencies added in M5 (checked from installed metadata)

courlan 1.4.0 (Apache-2.0), htmldate 1.11.0 (Apache-2.0), jusText 3.0.2 (BSD), lxml-html-clean 0.4.5
(BSD), dateparser 1.4.3 (BSD-3-Clause), ctranslate2 4.8.3 (MIT), onnxruntime 1.31.0 (MIT), av 19.0.1
(BSD-3-Clause), huggingface-hub 2.2.0, tokenizers 0.23.3 and hf-xet 1.7.0 (Apache-2.0), defusedxml
0.7.1 (PSF), protobuf (BSD-3-Clause), flatbuffers (Apache-2.0), requests (Apache-2.0), urllib3 (MIT),
regex (Apache-2.0 AND CNRI-Python), tqdm (MPL-2.0 AND MIT), httpx2/httpcore2 (BSD-3-Clause), and small
MIT/BSD utilities (PyYAML, filelock, fsspec, six, python-dateutil, pytz, tzlocal, babel, truststore).

**`tld` 0.13.2** (pulled in by courlan, which trafilatura requires) is offered as "MPL-1.1 OR GPL-2.0-only
OR LGPL-2.1-or-later". It is used here under its **MPL-1.1** option, as a library that is never
modified. MPL-1.1 is not on the §0 list; the owner approved this on 2026-10-14. Do not upgrade to a
version that drops the MPL option without re-checking.

## JavaScript (`frontend/package.json`)

| Package | Version | License |
|-|-|-|
| react, react-dom | 18.3.1 | MIT |
| vite | 8.3.4 | MIT |
| @vitejs/plugin-react | 6.1.2 | MIT |
| tailwindcss, @tailwindcss/vite | 4.3.3 | MIT |
| typescript | 6.0.3 | Apache-2.0 |
| vitest | 5.0.4 | MIT |
| jsdom | 29.1.1 | MIT |
| @testing-library/react | 16.3.3 | MIT |
| @testing-library/jest-dom | 7.0.1 | MIT |
| @testing-library/user-event | 14.6.8 | MIT |
| axe-core (dev) | 4.14.0 | MPL-2.0 (on the §0 list; used unmodified for the accessibility test) |
| eslint, @eslint/js | 10.12.0 / 10.0.1 | MIT |
| typescript-eslint | 8.71.2 | MIT |
| eslint-plugin-react-hooks | 7.1.1 | MIT |
| globals | 17.13.0 | MIT |
| prettier | 3.9.10 | MIT |
| @xyflow/react (React Flow) | 12.12.0 | MIT (its 19 transitive dependencies: MIT, ISC for d3-* modules, BSD-3-Clause for d3-ease) |
| react-markdown | 9.1.0 | MIT (its 81 transitive dependencies: MIT, plus one ISC) |
| @types/node, @types/react, @types/react-dom | 26.6.5 / 18.3.31 / 18.3.7 | MIT |

## External programs (called over HTTP or as a subprocess, not linked)

Ollama, Tesseract, ffmpeg. Detected by the setup wizard; not bundled.
