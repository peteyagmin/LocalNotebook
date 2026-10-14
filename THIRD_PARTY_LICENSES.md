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
| numpy | 2.5.4 | BSD-3-Clause (wheel also bundles components under 0BSD, MIT, Zlib, CC0-1.0) | M2 |

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
| eslint, @eslint/js | 10.12.0 / 10.0.1 | MIT |
| typescript-eslint | 8.71.2 | MIT |
| eslint-plugin-react-hooks | 7.1.1 | MIT |
| globals | 17.13.0 | MIT |
| prettier | 3.9.10 | MIT |
| react-markdown | 9.1.0 | MIT (its 81 transitive dependencies: MIT, plus one ISC) |
| @types/node, @types/react, @types/react-dom | 26.6.5 / 18.3.31 / 18.3.7 | MIT |

## External programs (called over HTTP or as a subprocess, not linked)

Ollama, Tesseract, ffmpeg. Detected by the setup wizard; not bundled.
