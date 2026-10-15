# LocalNotebook User Guide

LocalNotebook is a private research notebook that runs on your own computer. You give it your
documents, web pages and videos. You then ask questions and get answers that point back to the exact
passages they came from. It can also write summaries, timelines, mind maps, flashcards, and even a
spoken "podcast-style" audio overview of your material.

**Nothing leaves your computer unless you start an action that needs the internet** (such as adding a
web page). There is no account, no tracking, and no cloud service. The "brain" that reads and writes
is an AI model that you run yourself on your own machine.

LocalNotebook is an independent, open-source project. It is not affiliated with or endorsed by Google.
It is a local alternative to tools such as Google's NotebookLM.

This guide assumes you have never done anything like this before. Take it one step at a time.

---

## Contents

1. [How it works, in plain words](#1-how-it-works-in-plain-words)
2. [What you need](#2-what-you-need)
3. [Install the required programs](#3-install-the-required-programs)
4. [Get an AI model running (Ollama)](#4-get-an-ai-model-running-ollama)
5. [Download and start LocalNotebook](#5-download-and-start-localnotebook)
6. [First-time setup](#6-first-time-setup)
7. [Your first notebook, step by step](#7-your-first-notebook-step-by-step)
8. [Adding sources](#8-adding-sources)
9. [Asking questions (chat)](#9-asking-questions-chat)
10. [Searching your sources](#10-searching-your-sources)
11. [Notes](#11-notes)
12. [Generated documents and study aids (Studio)](#12-generated-documents-and-study-aids-studio)
13. [Audio overviews](#13-audio-overviews)
14. [Backing up, sharing and moving notebooks](#14-backing-up-sharing-and-moving-notebooks)
15. [Settings reference](#15-settings-reference)
16. [Keyboard shortcuts and accessibility](#16-keyboard-shortcuts-and-accessibility)
17. [Privacy and safety](#17-privacy-and-safety)
18. [Troubleshooting](#18-troubleshooting)
19. [Known limitations](#19-known-limitations)
20. [Glossary](#20-glossary)

---

## 1. How it works, in plain words

LocalNotebook has two parts that work together:

- **The app** (what you click on). It runs on your computer and shows up as a page in your web browser.
  The address looks like `http://127.0.0.1:12345`. That address only works on your own computer.
- **The AI model server** (the "brain"). By default this is a free program called
  [Ollama](https://ollama.com). It runs AI models on your computer. LocalNotebook sends it your
  questions and the relevant passages from your documents, and it writes the answers.

Two kinds of AI model are involved:

| Kind | What it does | Needed for |
|-|-|-|
| **Chat model** | Reads passages and writes answers, summaries, scripts | Everything that writes text |
| **Embedding model** | Turns text into numbers so the app can find the passages that match a question | Adding sources, asking questions, searching |

You choose both models yourself. Bigger models give better answers but need a stronger computer.

**Why you can trust the answers more than with a general chatbot:** LocalNotebook only answers from
your sources. Every claim carries a numbered citation chip, such as **[1]**. Click it and the source
opens at the exact passage. If your sources do not contain the answer, the app says so instead of
guessing.

---

## 2. What you need

### A computer

| | Minimum | Recommended |
|-|-|-|
| Memory | 16 GB RAM, a recent 8-core processor | 32 GB RAM and a graphics card with 12 GB or more of video memory, or an Apple Silicon Mac with 32 GB |
| What to expect | Everything works, but answers and audio take a while | Fast answers; a 10-minute audio overview in about 10 minutes |
| Disk space | About 10 GB free to start (models are large) | More if you keep many models and notebooks |

Windows, macOS and Linux are supported.

### Programs to install

| Program | What it is for | Required? |
|-|-|-|
| [uv](https://docs.astral.sh/uv/) | Installs and runs the app's Python parts for you | Yes |
| [Node.js](https://nodejs.org) (version 20 or newer) | Builds the app's web page the first time | Only if you download the source code instead of the ready-made release (see section 5) |
| [Git](https://git-scm.com/downloads) | Downloads the source code | Only for the source-code route |
| [Ollama](https://ollama.com/download) | Runs the AI models | Yes (or another compatible server) |
| [Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html) | Reads text from images and scanned PDFs | Only for images and scans |
| [ffmpeg](https://ffmpeg.org/download.html) | Builds the audio file | Only for audio overviews |
| [espeak-ng](https://github.com/espeak-ng/espeak-ng) | Helps the voices pronounce words | Only for audio overviews |

You can start with just uv and Ollama (plus Node.js and Git if you use the source-code route) and add the rest later. The app tells you, in plain language,
which features are switched off because something is missing.

### An internet connection (only for setup)

You need the internet to download the programs and models. After that, the app works offline. You
only need the internet again when you add a web page or video, use Discover, or download another
model.

---

## 3. Install the required programs

Do this part once. If you are not sure whether you already have something, install it anyway; it is
harmless to install again.

### Windows

1. Open the **Start menu**, type **PowerShell**, and open **Windows PowerShell**.
2. Copy and paste each line below, one at a time, pressing **Enter** after each. If Windows asks for
   permission, choose **Yes**.

   ```powershell
   winget install --id astral-sh.uv -e
   winget install --id OpenJS.NodeJS.LTS -e   # only for the source-code route
   winget install --id Git.Git -e             # only for the source-code route
   winget install --id Ollama.Ollama -e
   winget install --id UB-Mannheim.TesseractOCR -e
   winget install --id Gyan.FFmpeg -e
   winget install --id eSpeak-NG.eSpeak-NG -e
   ```

3. **Close PowerShell and open it again.** This step matters: programs are only found by a *new*
   window.

> If `winget` is not available, or one line fails, use the download links in the table in section 2
> instead. When an installer asks whether to "add to PATH", say **yes**.

### macOS

1. Install [Homebrew](https://brew.sh) if you do not have it (the page shows a single line to paste
   into **Terminal**; open Terminal from Spotlight with **Cmd+Space**, then type "Terminal").
2. In Terminal, paste:

   ```sh
   brew install uv node git tesseract ffmpeg espeak-ng
   brew install --cask ollama
   ```

3. Close Terminal and open it again.

### Linux (Ubuntu or Debian)

```sh
sudo apt update
sudo apt install git nodejs npm tesseract-ocr ffmpeg espeak-ng curl
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://ollama.com/install.sh | sh
```

If you will use the source-code route, check that Node.js is version 20 or newer with
`node --version`. If it is older, install a newer one from [nodejs.org](https://nodejs.org). Then close
the terminal and open it again.

### Check that it worked

In a **new** PowerShell or Terminal window, type each of these and press Enter. Each should print a
version number rather than an error such as "command not found":

```
uv --version
node --version      # only needed for the source-code route
ollama --version
tesseract --version
ffmpeg -version
espeak-ng --version
```

---

## 4. Get an AI model running (Ollama)

1. **Start Ollama.** On Windows and macOS, open the **Ollama** app from the Start menu or
   Applications (it sits in the system tray / menu bar). On Linux the installer starts it for you.
2. **Download two models.** In PowerShell or Terminal, use `ollama pull` followed by a model name.
   Browse the choices in the [Ollama model library](https://ollama.com/library).
   You need **one chat model** and **one embedding model**. For example (these are only examples;
   pick what suits your computer):

   ```
   ollama pull llama3.1
   ollama pull nomic-embed-text
   ```

   Here `llama3.1` is the chat model and `nomic-embed-text` is the embedding model. Each download can
   take several minutes and a few gigabytes.

   *How to choose:* a smaller chat model runs faster and works on modest computers; a larger one
   writes better. The library page shows each model's size. As a rule of thumb, pick a chat model
   whose download size is well under your RAM. Look for models described as good at following
   instructions, and for embeddings pick one marked "embedding".

3. **Check what you have:** `ollama list` prints your installed models. You will type these exact
   names into LocalNotebook in a moment.

> **Using something other than Ollama?** LocalNotebook works with any server that speaks the
> "OpenAI-compatible" format (for example LM Studio or a server you host). You can enter its address
> and key in Settings. If that address is not on your own computer, the app shows a yellow banner
> that says **"AI requests are being sent to …"** so you always know where your text is going.

---

## 5. Download and start LocalNotebook

### Download

**Easiest: the ready-made release (no Node.js needed).**

1. Open <https://github.com/peteyagmin/localnotebook/releases> and download the newest
   `LocalNotebook-v….zip`.
2. Unzip it. Open PowerShell or Terminal **inside the unzipped folder** (on Windows: open the folder in
   File Explorer, click the address bar, type `powershell`, and press Enter).

**Alternative: the source code (needs Git and Node.js).** Run:

```
git clone https://github.com/peteyagmin/localnotebook.git
cd localnotebook
```

The first start then also builds the web page, which takes a few extra minutes.

### Start

| Your computer | Command |
|-|-|
| Windows | `scripts\run.ps1` |
| macOS / Linux | `scripts/run.sh` |

**The first start takes a few minutes.** It downloads the app's parts (and, on the source-code route, builds the web page). You
will see lots of text scroll by. This is normal. It only happens the first time.

When it is ready, your web browser opens by itself on the app. In the window you started it from you
will see a line like:

```
LocalNotebook is running at http://127.0.0.1:53124/  (Ctrl+C to stop)
```

**Leave that window open** while you use the app. It is the app's engine.

> **Windows tip:** if PowerShell says running scripts is disabled, run this once and try again:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### Stop

Click in the window and press **Ctrl+C**. You can then close the window. Your notebooks are saved
automatically.

### Start it again later

Open PowerShell or Terminal, go to the `localnotebook` folder (`cd localnotebook`), and run the same
start command. Make sure Ollama is running first.

> **Why can't I bookmark the page?** Each time the app starts it picks a new private address and a
> one-time key, so that no other program or website on your computer can use it. Always start it with
> the command above and let it open the browser for you.

---

## 6. First-time setup

The first time the app opens you see the **setup checklist**. Each line shows a tick (✔) or a cross (✘)
and, for a cross, how to fix it.

| Line | What it means | If it has a cross |
|-|-|-|
| Model server reachable | The app can talk to Ollama | Start Ollama (section 4) |
| Chat model installed | The chat model you chose exists | Run the `ollama pull` command the app shows |
| Embedding model installed | Same, for the embedding model | Same |
| Tesseract (OCR) installed | Needed for images and scanned PDFs | Install Tesseract (section 3). Skip if you do not need it |
| ffmpeg installed | Needed for audio overviews | Install ffmpeg. Skip if you do not need it |
| espeak-ng installed | Needed for audio overviews | Install espeak-ng. Skip if you do not need it |

**Do this:**

1. Type the exact **Chat model** and **Embedding model** names from `ollama list` (for example
   `llama3.1` and `nomic-embed-text`).
2. Click **Save and re-check**.
3. When the first three lines show ✔, click **Continue**. The other lines can wait.

You can come back to all of this any time from **Settings** (top right).

**Important setting: the context window.** In **Settings → Models** there is *Model context window
(tokens)*. It tells the app how much text your chat model can read at once. The default (8000) is safe
for most models. If you know your model supports more (the model's page on Ollama says), a larger
number lets the app write bigger documents in one go.

---

## 7. Your first notebook, step by step

A **notebook** is a project folder. Everything in it (sources, chats, notes, generated documents) is
kept together and answers only come from the sources in that notebook.

1. On the home screen, click **New notebook**, type a name such as "Climate research", and click
   **Create**. The notebook opens.
2. The notebook has three panels:

   | Panel | Where | What it does |
   |-|-|-|
   | **Sources** | Left | Your documents. Add, tick or untick, and open them |
   | **Chat** | Middle | Ask questions here |
   | **Studio** | Right | Notes, summaries, timelines, flashcards, audio |

   You can drag the thin lines between panels to resize them, and use the small **«** **»** buttons to
   collapse a panel.

3. Click **Add source → Upload files**, choose a PDF or text file, and wait until its name turns from
   grey to a normal clickable link. That means it is *ready* (a few seconds to a few minutes,
   depending on size and your computer).
4. Click the file's name to open it and read the one-paragraph guide the app wrote about it.
   Press **Esc** to close it.
5. In the chat box type a question about your document and press **Enter**. The answer streams in
   with numbered chips like **[1]**.
6. Click a chip. The source opens with the supporting passage highlighted.

That is the whole core idea. The rest of this guide covers each part in more depth.

---

## 8. Adding sources

Click **Add source** at the top of the Sources panel. Choose one:

| Option | Use it for |
|-|-|
| **Upload files** | PDF, Word (.docx), text (.txt), Markdown (.md), HTML, EPUB books, images (.png, .jpg), and audio (.mp3, .wav, .m4a). You can pick several at once |
| **Paste text** | Text you copy from somewhere. Give it a name |
| **Website** | One or more web addresses (one per line). The page's main text is saved so it works offline afterwards |
| **YouTube** | A video address. Uses the video's captions |
| **Discover** | Describe a topic and get suggestions of pages and videos to add |

**Limits (you can change them in Settings):** 50 sources per notebook, 200 MB per file.

### Source states

Each source shows its state while the app reads it: *waiting*, *processing* (with a progress bar),
*ready* or *failed*. A failed source shows why and has a **Retry** button. Common reasons: the model
server is not running, or no embedding model is set.

### Turning sources on and off

Each source has a tick box. **Only ticked sources are used** for answers, searches and generated
documents. Untick a source to leave it out without deleting it. **Select all** ticks everything.

### Removing a source

Click the **✕** next to a source and confirm. Notes and chats that cited it keep their text, and the
citation shows as "source removed". Generated documents that used it show a "Sources changed —
regenerate?" notice.

### Special cases

**Images and scanned PDFs.** The app reads text from pictures with Tesseract (section 3). Without it,
the rest of the app works and **Upload files** tells you this feature is off.

**Audio files and videos without captions.** These need a *speech-to-text model*:

1. Open **Settings → Speech to text** and type a model name. Small names like `tiny` or `base` are
   fast; `small` or larger are more accurate. The speech model is a
   [faster-whisper](https://github.com/SYSTRAN/faster-whisper) model.
2. Click **Save**, then **Download model**. The app asks you to confirm because it uses the internet,
   and shows a progress bar.
3. Now audio files can be added. For YouTube videos with no captions, also tick **Transcribe videos
   without captions** (off by default). That downloads only the sound, turns it into text on your
   computer, and deletes the sound. *You are responsible for following the video platform's terms of
   service.*

Citations for audio and video show a **time** (such as 12:34) instead of a page.

**Websites and refreshing.** Pages are saved when you add them. To get a newer version, click
**Refresh from web** on that source. The older capture is kept: open the source and use the
**Version** menu to read an earlier version. If a refresh fails, the source stays usable with its
previous capture and shows what went wrong.

**Web addresses on your own network are blocked.** For safety, the app refuses addresses like
`localhost` or `192.168.x.x`. Only public web pages can be added.

**Discover.** This needs a search provider you run yourself,
[SearXNG](https://docs.searxng.org) (advanced; skip it if you do not use it). Enter its address under
**Settings → Network** with JSON output enabled. Discover then suggests up to 10 pages or videos for a
topic. **Nothing is added until you tick the ones you want and confirm.**

---

## 9. Asking questions (chat)

Type in the box at the bottom of the middle panel.

- **Enter** sends. **Shift+Enter** starts a new line.
- Answers stream in word by word. Click **Stop** if you have seen enough; the partial answer is kept
  and marked *Stopped*.
- Under each answer the app offers **suggested follow-up questions**. Click one to ask it.
- A notebook with ready sources also offers **starter questions** before you have asked anything.

### Citations

The numbered chips **[1] [2]** are links to the supporting text. Click one to open the source with
that exact passage highlighted. Hovering over a chip, or tabbing to it, shows the source name and a short excerpt. If the source was
removed later, the chip says so.

### When the answer is not in your sources

LocalNotebook will say it cannot find that in your sources instead of making something up. If you
expected an answer: check that the right sources are ticked, that they are *ready*, and try rewording
the question.

### Chat settings

Click **Chat settings** under the box:

- **Response style:** Default, Concise, Detailed, or Learning guide (explains step by step).
- **Custom instruction:** a sentence the app follows in every answer, such as "Answer in Spanish" or
  "Explain like I am new to this topic".

### Save an answer

Click **Save to note** under any answer to keep it, with its citations, in your Notes.

### Clear chat

**Clear chat** wipes the conversation for this notebook after you confirm. Your sources and notes are
not affected.

---

## 10. Searching your sources

Use the search box at the top of the notebook (or press **Ctrl+K** on Windows/Linux, **Cmd+K** on Mac).
It searches the text of your sources **and** your notes. Results show the source, the location (page,
heading or time), and the matching words highlighted. Click one to open that exact spot. Press
**Esc** to clear the search.

This is different from chat: search shows you the original passages; chat writes an answer from them.

---

## 11. Notes

Notes are your own writing area, inside the **Studio** panel.

- Click **New note** to start one. It saves by itself a moment after you stop typing.
- Notes can include citations. When you **Save to note** from a chat answer, the chips come with it.
- Notes are searchable together with your sources.
- Tick one or more notes to get actions:
  - **Summarize** makes a new note summarizing the ticked ones.
  - **Combine into one note** merges them into a new note.
  - **Convert to source** turns a note into a source that chat can use.

  The originals are always kept.

---

## 12. Generated documents and study aids (Studio)

In the **Studio** panel, click a button to have the app write something from all ticked sources.
It starts working in the background and shows a progress bar, so you can keep using the app.
You can **Cancel** while it runs.

| Button | What you get |
|-|-|
| **Summary** | A short overview with citations |
| **Briefing** | A structured briefing document |
| **Study guide** | Key ideas, terms and review questions |
| **FAQ** | Likely questions and answers |
| **Timeline** | Dated events (and the people involved) in order |
| **Mind map** | An expandable map of topics. Click a node to ask the chat about it |
| **Flashcards & quiz** | Flip-cards and a multiple-choice quiz with a score. Small notebooks get a shorter quiz |
| **Audio overview** | A spoken two-host discussion (see section 13) |

**Focus (optional):** type a short instruction in the *Focus* box first (for example "only the
financial parts") and the document concentrates on it.

### Reading, regenerating and exporting

Click a finished item in the list to open it. Use **Expand** to give it the full width and **← Back**
(or **Esc**) to close it.

- **Regenerate** writes a new version. If it fails, the old version is kept.
- A **"Sources changed — regenerate?"** notice means you added, removed or unticked sources after it
  was written.
- **Export** saves a file:
  - Text documents: Markdown (.md), Word (.docx) or PDF.
  - Timeline: also JSON.
  - Mind map: PNG picture or JSON.
  - Flashcards and quiz: CSV files (for importing into flashcard apps) or JSON.
  - Audio overview: MP3.

### If you have lots of sources

If your sources are too big for the model to read at once, the app first condenses them in parts
and then writes from those notes. This works but takes longer. Setting a larger *Model context window*
(section 6) helps when your model supports it.

---

## 13. Audio overviews

An audio overview is like a short podcast in which two hosts discuss your sources, with citations
kept in the transcript.

### One-time preparation

You need all of these. The Studio's **Audio overview** box lists anything missing under
**What is missing**, and the **Generate audio overview** button stays grey until everything is ready.

1. **ffmpeg** and **espeak-ng** installed (section 3).
2. A **text-to-speech model** and **two voices**. Open **Settings → Text to speech** and fill in:
   - *Text-to-speech model*: the address of a Kokoro model on [Hugging Face](https://huggingface.co),
     in the form `owner/name`. LocalNotebook is designed for **Kokoro in ONNX format**, for example
     `onnx-community/Kokoro-82M-v1.0-ONNX`.
   - *Voice for Host A* and *Voice for Host B*: the names of two voices that model offers, such as
     `af_heart` and `am_adam`. Browse the model's `voices` folder on its Hugging Face page to see the
     names.
3. Click **Save**, then **Download model and voices**. Confirm, and wait for the progress bar.

These names are examples. This text-to-speech feature was built to the published Kokoro layout but
has not yet been tested on real model files by the developer, so if the download or the first audio
fails, note the message the app shows and report it.

### Make one

1. In Studio, under **Audio overview**, choose:
   - **Length:** Short (~5 min), Default (~10 min), or Long (~20 min).
   - **Format:**
     - *Deep dive* – a friendly, thorough discussion
     - *Brief* – the essentials, quickly
     - *Debate* – hosts take different sides
     - *Critique* – hosts assess strengths and weaknesses of the material
   - Optionally, type a **Focus**.
2. Click **Generate audio overview**. It writes a script, then speaks it. This is slow on ordinary
   computers (a 10-minute episode can take about 10 minutes or more). Keep the app open. You can
   continue using other parts and **Cancel** if you change your mind.

### Listen

Open the finished item. The player has:

- **Play / Pause**, a **seek bar**, **back 15 seconds** and **forward 15 seconds**,
- **Speed** from 0.75× to 2×,
- a **transcript** that highlights the line being spoken. **Click any line** to jump there.

### Fix the script without starting over

If a line is wrong, you do not need to regenerate everything:

1. Click **Edit script**. For each line you can change the text, change which host says it, move it
   up or down, or delete it.
2. Click **Save script**. A notice says the audio is out of date.
3. Click **Re-synthesize audio**. Only the speaking is redone, using your edited script. It is much
   faster than a brand-new overview.

Export the MP3 from the **Export** menu.

---

## 14. Backing up, sharing and moving notebooks

### Export a notebook (backup or share)

On the home screen, click **Export** on a notebook's card. Your browser saves a single `.lnb` file
containing everything: sources, chats, notes, generated documents and audio.

### Import a notebook

On the home screen, click **Import notebook** and choose a `.lnb` file. It works across Windows,
macOS and Linux, and between computers. **Importing never overwrites anything.** If a notebook with
the same identity already exists, you get a second one named "… (copy)".

You can move your work to a new computer this way: install LocalNotebook there (sections 3–6), then
import your `.lnb` files.

> Sources and models are in the file; AI models themselves are not. On the new computer, install
> Ollama and your models again. If the new computer uses a different *embedding model*, see "Rebuild
> index" below.

### Other notebook actions

On each card: **Rename**, **Duplicate** (a full copy) and **Delete** (asks you to confirm; this
cannot be undone, so export first if unsure).

### Rebuild index

If you change the **embedding model** in Settings, existing notebooks show a yellow notice and a
**Rebuild index** button. Click it so that searching and answers use the new model. It re-reads every
source and note, so it may take a while. Rebuild is only needed after changing the embedding model.

### Where your data lives

Everything is stored in one folder on your computer:

| System | Folder |
|-|-|
| Windows | `C:\Users\<you>\AppData\Local\LocalNotebook\LocalNotebook` |
| macOS | `~/Library/Application Support/LocalNotebook` |
| Linux | `~/.local/share/LocalNotebook` |

Inside, `notebooks` has one folder per notebook and `models` holds downloaded speech models. To
choose a different folder, set the environment variable `LNB_DATA_ROOT` before starting the app. To
back up everything at once, close the app and copy that folder.

---

## 15. Settings reference

Open **Settings** from the top right of any screen. Click **Save** after changes.

| Section | Setting | What it does |
|-|-|-|
| **Appearance** | Theme | Same as the computer, Light, or Dark |
| | Text size | Small to Largest |
| **Model server** | Model server URL | Where your AI server is. Default `http://127.0.0.1:11434/v1` is Ollama on this computer |
| | API key | Only if your server needs one |
| **Models** | Chat model, Embedding model | The names from `ollama list` |
| | Model context window | How much text the chat model reads at once |
| | Passages used per answer | How many source excerpts feed each answer (default 8) |
| **Speech to text** | Speech-to-text model + Download | For audio files and uncaptioned videos |
| | Transcribe videos without captions | Off by default |
| **Text to speech** | Model, Host A voice, Host B voice + Download | For audio overviews |
| **Limits** | Maximum sources per notebook, maximum file size | Defaults 50 and 200 MB |
| **Network** | Import web pages and videos | Turn off to forbid any web fetching |
| | Discover sources | Turn off to disable Discover |
| | Search provider address | Your SearXNG address |
| | Download speech models | Turn off to forbid model downloads |

**Test connection** checks that the app can reach your model server and lists the models it found.

---

## 16. Keyboard shortcuts and accessibility

| Keys | Action |
|-|-|
| **Enter** | Send your question |
| **Shift+Enter** | New line in the question box |
| **Esc** | Close the newest open menu, dialog or panel (source viewer, a document, a menu) |
| **Ctrl+K** (Cmd+K on Mac) | Jump to the search box |
| **Tab / Shift+Tab** | Move between controls |

Everything can be used with the keyboard, buttons have text labels for screen readers, and keyboard
focus is always visible. Change the look in **Settings → Appearance**: Light, Dark, or follow your
computer, and a larger text size.

---

## 17. Privacy and safety

- **Your documents stay on your computer.** The app has no accounts, analytics or update checks.
- **Where the internet is used:** only when *you* add a web page or video, run Discover, or download a
  speech model; plus calls to your AI server. Each of these can be switched off in **Settings →
  Network**. If your AI server address is not on your own computer, a banner tells you.
- **The app only listens to your own computer** (`127.0.0.1`), and each launch uses a new secret key,
  so other websites and programs cannot use it.
- **Documents are treated as untrusted.** Instructions hidden inside a document ("ignore the rules and
  …") are treated as ordinary text, not commands.
- **Web safety:** addresses on your own network or computer are refused, so the app cannot be tricked
  into probing your network.
- The `.lnb` files you export are **not encrypted**. Treat them like the original documents.
- **Your data folder is not encrypted either**, and the optional model-server API key (if you use
  one) is stored there as plain text. Protect the folder the way you protect your other personal
  files (for example with your computer's disk encryption).

---

## 18. Troubleshooting

| What you see | What to try |
|-|-|
| A command is "not found" (`uv`, `node`, …) | Close and reopen PowerShell/Terminal after installing. If still missing, reinstall that program and allow "add to PATH" |
| `scripts\run.ps1` is blocked on Windows | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once |
| The browser did not open | Copy the `http://127.0.0.1:…` address from the window where you started the app into your browser. If it says "not authorised", close the app (Ctrl+C) and start it again so a fresh link opens |
| "Model server reachable" has a cross | Start the Ollama app and check the address in Settings → Model server. **Test connection** shows the result |
| Setup says a model is "not installed" | Run the `ollama pull <name>` command the app displays. The name must match exactly |
| A source says **failed** | Read the message under it. Then fix the cause (usually the server or models) and click **Retry** |
| Sources stay "processing" for a long time | Large files and slow computers take time. Check the window where the app runs for errors; the first embedding of a big file can be slow |
| Images or scans show as failed | Install Tesseract (section 3) and restart the app |
| A web page will not import | Some sites block automatic reading, or need a login; try copying the text and using **Paste text**. Local addresses are always refused |
| A YouTube video "has no captions" | Either choose a video with captions, or set up speech-to-text and tick **Transcribe videos without captions** (section 8) |
| Chat says it cannot find the answer | Check the sources are ticked and *ready*; try different wording; add the missing material |
| Answers are slow | Normal on computers without a graphics card. Try a smaller chat model |
| Answers are poor or ignore the sources | Try a larger or better instruction-following chat model, or reduce the number of ticked sources |
| Generate audio overview is grey | Read the **What is missing** list under it and do those steps (section 13) |
| Text looks too small or too bright | **Settings → Appearance** |
| After changing the embedding model, search is odd | Click **Rebuild index** on the notebook |
| Port or folder conflicts | Set `LNB_HOST_PORT` (a fixed port) or `LNB_DATA_ROOT` (data folder) before starting |
| Everything looks broken after an update | Close the app, then in the `localnotebook` folder run `cd frontend`, `npm ci`, `npm run build`, and start again |

If something still goes wrong, the window where you started the app prints technical messages. Copy
them when asking for help or reporting a problem at
<https://github.com/peteyagmin/localnotebook/issues>.

---

## 19. Known limitations

Please be aware of these in version 1.0:

- **Audio overviews are the least-tested feature.** The voice engine was written to the published
  Kokoro format but has had limited testing on real model files. If it fails, the app shows an error
  message and nothing else is affected.
- **Answer quality depends on your model.** Small models on modest computers can miss details or
  phrase things poorly. The citations let you check every claim.
- **Windows and macOS** are supported, but most testing has been on Linux. Report anything odd.
- **Speed** depends heavily on your hardware. Without a graphics card, chat and audio are slow.
- **Videos and web pages** depend on outside sites. Sites can block automatic reading, and YouTube
  changes often; if video import breaks, update to the newest release.
- Notebooks and exports are **not encrypted**, and there is no sync between computers other than
  exporting and importing a notebook.

---

## 20. Glossary

| Word | Meaning |
|-|-|
| **Notebook** | A project that holds your sources, chat, notes and generated items |
| **Source** | A document, web page, video, audio file or pasted text you add |
| **Ready** | A source the app has finished reading and can use |
| **Citation / chip** | A numbered link, like [1], from an answer to the passage that supports it |
| **Studio** | The right-hand panel for notes and generated documents |
| **Artifact** | Anything generated in Studio (a summary, timeline, audio overview, …) |
| **Model** | The AI program that reads and writes. Runs on your computer |
| **Chat model / Embedding model** | The model that writes text / the model that finds matching passages |
| **Ollama** | A free program that runs AI models on your computer |
| **Context window** | How much text a model can read at once |
| **Index** | The app's searchable catalogue of your sources |
| **OCR** | Reading text out of pictures (done by Tesseract) |
| **Speech-to-text / Text-to-speech** | Turning sound into words / words into spoken sound |
| **`.lnb` file** | An exported notebook (a ZIP file with a different name) |
| **PATH** | The list of places your computer looks for programs. Installers add to it when you say yes |
