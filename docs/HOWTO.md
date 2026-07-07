# salient-tutor — How-to / Getting Started

A full walkthrough: install → configure → run → your first session → troubleshooting.
For *what it is* and the architecture, see the [README](../README.md).

---

## 1. Prerequisites

- **Python 3.11+**
- **An Anthropic API key** (the tutor orchestrates Claude). Export it as `ANTHROPIC_API_KEY`.
- **git** (the kernel is installed from a repo, not PyPI).
- Optional: a **MiniMax** and/or **GLM (z.ai)** key for cloud image generation and read-aloud; a local **ComfyUI** box for on-device images; an **LM Studio** endpoint to run the document parser locally.

---

## 2. Install

salient-tutor rides on the `salient-core` kernel. Install the kernel first, then the tutor.

### With the public kernel (`salient-core-public`)

```bash
# 1) the kernel — editable clone …
git clone https://github.com/baggybin/salient-core-public.git
pip install -e salient-core-public/
#    … or straight from git:
# pip install "git+https://github.com/baggybin/salient-core-public.git"

# 2) the tutor
git clone https://github.com/baggybin/salient-tutor.git
pip install -e salient-tutor/
```

The tutor declares a **bare** `salient-core` dependency (no version pin) precisely so it accepts whichever kernel build you install — public `0.4.x`, a private checkout, editable or from git. It's verified green against `salient-core-public` v0.4.0.

### Optional extras

```bash
pip install -e "salient-tutor/[dev]"      # ruff + pytest (to run the test suite)
pip install -e "salient-tutor/[images]"   # local ComfyUI/flux diffusion (the `imagegen` package)
```

Local on-device images need the `imagegen` package **and** a reachable ComfyUI box. If it's absent the app still boots — image generation just reports "unavailable," and you can use the cloud providers instead (§3).

---

## 3. Configure

Everything is an environment variable; the app reads them at startup and degrades gracefully when one is absent. **Minimum to run:**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export TUTOR_MODEL=claude-opus-4-8[1m]     # a model your key can access
```

Then add only what you want. The server logs which optional features came up (e.g. `image generation: on — cloud: minimax-image, glm-image`), so you can confirm a key was picked up.

### Models & agents

| Variable | Effect |
|---|---|
| `TUTOR_MODEL` | The tutor orchestrator model (default `claude-opus-4-8[1m]`). |
| `TUTOR_PROVIDER` | Provider for the tutor (default anthropic). |
| `TUTOR_LIBRARIAN_MODEL` | The librarian (document read/structure) agent's model. Can be re-pointed at a local endpoint from the ⚙ modal. |
| `TUTOR_JUDGE_MODEL` | Enables the **judge** (attempt-first gate + answer-leakage filter). Unset → live streaming, no gate. |
| `TUTOR_VARIANT_MODEL` / `_PROVIDER` / `_LABEL` | Registers a shadow "variant" tutor on a second model; the web modal shows a picker (try `claude-fable-5[1m]`). Needed for the second-opinion consensus panel. |

### Images — opt-in (`TUTOR_IMAGES=1`)

Mnemonic images are **off by default**. Turn the channel on, then configure at least one backend (local, cloud, or both). In the app, pick a model from the **art dial** (cloud models carry a ☁ mark).

```bash
export TUTOR_IMAGES=1
```

| Variable | Backend |
|---|---|
| *(the `[images]` extra + a ComfyUI box)* | **Local** flux / qwen on your GPU (deterministic, free). |
| `MINIMAX_API_KEY` (`MINIMAX_API_HOST`) | **MiniMax** `image-01` cloud. Same key as read-aloud. |
| `GLM_API_KEY` **or** `ZHIPU_API_KEY` | **GLM** cloud (z.ai `glm-image`). `GLM_API_HOST` (default `https://api.z.ai/api/paas/v4`; use `https://open.bigmodel.cn/api/paas/v4` for China) and `GLM_IMAGE_MODEL` (default `glm-image`; e.g. `cogview-4`) override. |
| `TUTOR_IMAGE_CACHE` | Override where PNGs are cached (default `<workspace>/images`). |

Cloud renders are **~pay-per-use**; a re-shown image is served from disk (content-addressed cache + artifact index), so a reload never re-bills.

### Read-aloud (TTS) — optional

| Variable | Effect |
|---|---|
| `MINIMAX_API_KEY` (`MINIMAX_API_HOST`, `MINIMAX_GROUP_ID`) | Enables per-message read-aloud (MiniMax T2A). Absent → the audio UI is hidden. |
| `TUTOR_TTS_CACHE=1` (`TUTOR_TTS_CACHE_DIR`, `TUTOR_TTS_CACHE_MAX_MB`) | Cache synthesized audio on disk. |

### Embeddings (semantic recall over study docs) — optional

| Variable | Effect |
|---|---|
| `SALIENT_EMBED_BASE_URL` / `SALIENT_EMBED_MODEL` / `SALIENT_EMBED_API_KEY` | Default embeddings endpoint/model/key. The ⚙ Settings modal overrides these at runtime. |

### Workspace & misc

| Variable | Effect |
|---|---|
| `TUTOR_WORK_ROOT` | Workspace directory (chats, KG, gradebook, images). Default `<repo>/work`. A relative path resolves against the repo root. Also settable per-launch with `--work-root`. |
| `TUTOR_DIAGRAM_PLANTUML=1` | Enable the PlantUML diagram engine (sandboxed; off by default). |

---

## 4. Run

### Web app (recommended)

```bash
python -m salient_tutor.web --port 8000
# → open http://localhost:8000
```

Flags: `--host` (default `127.0.0.1`), `--port` (default `8000`), `--work-root` (workspace dir; overrides `$TUTOR_WORK_ROOT`). A plain launch **autoloads the last-used workspace**.

### CLI (one-shot)

```bash
salient-tutor "teach me about photosynthesis"
salient-tutor --agent librarian "..."      # address the librarian
salient-tutor --work-root work/alice "..."  # a specific profile
```

---

## 5. Your first session (web)

1. **Ask for a lesson.** Type e.g. *"teach me the OSI model."* The tutor runs the **9-phase lesson loop** (Diagnose → Objective → Model → Check → Anchor → Drill → Reflect → Cards → Elaborate) and won't advance until you demonstrate the concept in a fresh case. Diagrams (Mermaid) render inline with step-through.
2. **Get graded / spaced.** As you're checked, mastery lands in the **skill-map rail** (due/strong/weak/mastered, with recall-odds and a review-load forecast). Click a topic to drill it; the retrieval micro-quiz records an SM-2 review.
3. **Turn on images (optional).** With `TUTOR_IMAGES=1` and a backend configured, pick a model in the **art dial** (◇ No art → a flux/qwen/MiniMax ☁/GLM ☁ model). Now the tutor may include a mnemonic image; images persist and won't regenerate on reload.
4. **Build a memory palace.** Ask *"build me a memory palace for the TCP handshake."* You get a spatial walk of loci, each a **recall ladder**: read the locus → **💡 Hint** (the metaphor) → **Reveal** (image + the element→fact mapping) → grade **Again/Hard/Good/Easy**. Grades feed the *same* SM-2 gradebook.
5. **Teach from your own document (Library tab).** Create a study project, **upload** a PDF/markdown, and the **librarian** extracts and structures it (live progress streams as it reads). Then teach straight from the document's own sections; `semantic_recall` surfaces the right passages.
6. **Second opinion (optional).** With a `TUTOR_VARIANT_MODEL` (and/or judge) configured, ask for a consensus panel — two models answer, you get an agreement score + corroborated/divergent findings.
7. **Read-aloud (optional).** With `MINIMAX_API_KEY` set, each tutor message gets a 🔊 control.

### Workspaces ("schoolbags")

Everything for one profile — chats, KG, gradebook, review logs, images — lives under one workspace directory. Run isolated profiles by pointing at different dirs:

```bash
python -m salient_tutor.web --port 8000 --work-root work/alice
python -m salient_tutor.web --port 8001 --work-root work/bob
```

To reset a profile: stop the server, delete/rename its directory, restart (a fresh one is created).

---

## 6. Verify your install

```bash
pip install -e "salient-tutor/[dev]"
cd salient-tutor
pytest -q          # full suite
ruff check src/ tests/
```

Green here means the tutor is wired correctly to whichever `salient-core` you installed.

---

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| **"not connected — reconnecting…"** on send | You submitted before the WebSocket finished its handshake; the turn is queued and auto-sends when it opens. Just wait a beat / it self-recovers. |
| **Art dial doesn't appear** / no image options | `TUTOR_IMAGES` isn't `1`, or no backend is configured. Check the startup log line `image generation: …`. |
| **Image card shows an error** | The card shows the provider's real message and degrades to caption-only (nothing breaks). Cloud 4xx is usually a bad key, a model your account lacks, or a content refusal. |
| **GLM `模型不存在` / model-not-found (400)** | Wrong endpoint/model for your account. On z.ai use `glm-image` (default); set `GLM_IMAGE_MODEL=cogview-4` or `GLM_API_HOST=…open.bigmodel.cn…` for the China platform. |
| **A key looks ignored** | It must be in the **process** environment of the server (no `.env` autoload). Confirm via the `image generation: …` startup line. |
| **Images "regenerate" on reload** | Fixed — a content-keyed artifact index serves the original from disk. Images made *before* the index (or after a style edit) regenerate **once**, then are stable. |
| **Extraction seems stuck** | The Library panel streams the librarian's live activity (reading → tool-calls → writing). A minute is normal for a dense PDF. |
| **`salient-core` install fails with "No matching distribution"** | The kernel isn't on PyPI — install it from git or an editable clone (§2). Don't add a PEP 440 version pin; it forces pip to query PyPI where the package doesn't exist. |
