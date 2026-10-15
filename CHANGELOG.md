# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/),
and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-15

First public release.

### Added
- **Notebooks:** create, rename, duplicate, delete; one self-contained folder each.
- **Sources:** PDF, Word, text, Markdown, HTML, EPUB, images and scanned pages (Tesseract OCR),
  audio files (local speech-to-text), web pages (saved for offline use, refresh keeps earlier
  versions), YouTube videos (captions, or local transcription if enabled), pasted text, and
  Discover (suggestions through your own SearXNG server).
- **Cited chat:** answers only from your sources, numbered citations that open the passage,
  suggested questions, Stop, response styles and a custom instruction, save answer to note.
- **Search** across sources and notes (`Ctrl/Cmd+K`).
- **Notes:** autosave, summarize, combine, convert to a source.
- **Studio:** summary, briefing, study guide, FAQ, timeline, mind map, flashcards and quiz, with
  export to Markdown, Word, PDF, PNG, JSON and CSV. Large notebooks are condensed to fit the model.
- **Audio overviews:** two-host script, text-to-speech (Kokoro ONNX with espeak-ng), MP3, player
  with synced transcript, script editing and re-synthesis.
- **Export and import** of notebooks as `.lnb` files; imports never overwrite.
- **Rebuild index** after changing the embedding model.
- **Settings:** model server and models, speech models with confirmed downloads, network switches,
  limits, light/dark theme and text size.
- Suggested default models: `llama3.1` (chat) and `nomic-embed-text` (embeddings), changeable in Settings.
- Setup checklist for the model server, models, Tesseract, ffmpeg and espeak-ng.
- Security: server on `127.0.0.1` only, per-launch token, origin check, sandboxed parsers, URL
  safety checks that refuse local and private addresses.
- Accessibility pass (axe-core in light and dark themes), keyboard shortcuts.
- Test suite (unit, browser smoke and accessibility tests) and a performance check script.

### Known limitations
- Audio overviews have had limited testing on real Kokoro model files.
- The grounding evaluation has not been run against any specific real model for this release.
- Most testing was done on Linux; Windows and macOS are covered by CI only.
- Notebooks, exports and the optional API key are stored unencrypted.
