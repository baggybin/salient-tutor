"""Memory-palace playground — local GPU renderer + interactive recall viewer.

A throwaway *playground* to perfect the method-of-loci UX before baking it into
the real app (web/static/js/tutor.js). It mirrors the vetted integration design
(see docs/MNEMONIC_INTEGRATION_PLAN.md), so this file doubles as the reference
implementation for the app port:

  * VETTED SCHEMA — each locus carries locusPhrase (the mundane, verbatim-reused
    anchor), metaphorAnchor (the abstraction bridge / pre-reveal hint), scene
    (the ONE-bizarre-element diffusion prompt), caption (the element->fact
    MAPPING, shown post-reveal), technicalFact, and optional callbackTo.
  * DISCIPLINED-BIZARRE — every scene has exactly ONE impossible element on the
    target against an otherwise mundane setting (von Restorff isolation), a
    transitive action mid-doing, and NO in-image text (flux leaks gibberish).
  * mode="loci" — renders through the surreal-tolerant negative profile.
  * RECALL LADDER — the viewer is a real active-recall FSM (HIDDEN -> HINTED ->
    ATTEMPTED -> REVEALED -> MASTERED), not a click-to-reveal toy. In the app
    the grade buttons call record_review() (SM-2 gradebook); here they persist
    to localStorage so you can feel the loop. Vanilla JS + D3 (no React), to
    match the app's stack.

Usage:
    python tools/build_memory_palace.py --local-gpu            # full palace, flux-dev
    python tools/build_memory_palace.py --local-gpu --fast     # flux-schnell (~10s/img)
    python tools/build_memory_palace.py --local-gpu --limit=2  # first 2 loci only
    python tools/build_memory_palace.py                        # rebuild HTML only (no render)
"""

import asyncio
import json
import shutil
import sys
from pathlib import Path

# ── The palace (vetted schema; OAuth 2.0 + PKCE, "The Velvet Rope Casino") ─────
# Each scene: mundane setting + ONE impossible element ON the target concept +
# a transitive action, zero text. caption states the element->fact MAPPING.
PALACE = {
    "version": 1,
    "palaceId": "oauth-pkce-casino",
    "palaceTheme": "A hushed, velvet-and-brass members-only casino at night.",
    "topic": "OAuth 2.0 Authorization Code flow with PKCE",
    "rooms": [
        {
            "roomId": "room-valet",
            "roomName": "The Valet Stand",
            "conceptTaught": "The client app starts the flow and commits a PKCE secret.",
            "loci": [
                {
                    "locusId": "locus-app-request",
                    "locusPhrase": "the brass call-bell on the valet podium",
                    "metaphorAnchor": "The app asking for access = a valet who won't move until you sign.",
                    "scene": "A valet in a plain uniform blocks a podium, holding out a single fountain pen that has grown as long and thick as a pool cue, pressing its glowing nib toward your open hand until you take it. Everything else is ordinary. Centered medium shot.",
                    "caption": "The absurd pool-cue-sized pen pressed on you = the client app demanding access before anything else can happen.",
                    "technicalFact": "The client application initiates the flow by requesting access to the user's resources.",
                    "callbackTo": None,
                },
                {
                    "locusId": "locus-pkce-commit",
                    "locusPhrase": "the coat-check counter beside the podium",
                    "metaphorAnchor": "PKCE = tear a ticket in half, lock your half away, hand over the other.",
                    "scene": "At an ordinary coat-check counter you tear a paper ticket in half; one half bursts into cold blue flame and drifts down into a locked glass jar, while you hand the plain other half across the counter. One impossible element: the burning half. Centered shot.",
                    "caption": "The burning half sealed in the jar = the secret Code Verifier; the plain half you hand over = its hashed Code Challenge.",
                    "technicalFact": "The client generates a secret Code Verifier and sends only the hashed Code Challenge, so an intercepted code is useless.",
                    "callbackTo": None,
                },
            ],
        },
        {
            "roomId": "room-desk",
            "roomName": "The Bouncer's Desk",
            "conceptTaught": "The user authenticates, consents, and receives a short-lived code.",
            "loci": [
                {
                    "locusId": "locus-authn",
                    "locusPhrase": "the velvet rope and clipboard at the desk",
                    "metaphorAnchor": "Authentication = the bouncer proving it's really you, not the app.",
                    "scene": "A tuxedoed bouncer leans over a desk and presses a glowing rubber stamp shaped like a single giant eyeball against your forehead. The rest of the desk is mundane. Centered medium shot.",
                    "caption": "The eyeball stamp on YOUR forehead = you authenticating directly with the Authorization Server, not the app.",
                    "technicalFact": "The user authenticates directly with the Authorization Server; the app never sees the credentials.",
                    "callbackTo": None,
                },
                {
                    "locusId": "locus-code-issue",
                    "locusPhrase": "the pneumatic tube slot on the desk",
                    "metaphorAnchor": "Authorization Code = a claim ticket that's already melting.",
                    "scene": "The bouncer drops a single ice cube stamped like a poker chip into a brass pneumatic tube; it whooshes upward, already dripping and shrinking. One impossible element: the melting chip. Centered shot.",
                    "caption": "The melting ice-chip shooting up the tube = the short-lived, single-use Authorization Code sent back to the app.",
                    "technicalFact": "The server sends a short-lived, single-use Authorization Code back to the app's redirect URI.",
                    "callbackTo": None,
                },
            ],
        },
        {
            "roomId": "room-office",
            "roomName": "The Back Office",
            "conceptTaught": "The app trades the code (plus its secret) for a token, privately.",
            "loci": [
                {
                    "locusId": "locus-token-exchange",
                    "locusPhrase": "the steel mail slot in the back-office door",
                    "metaphorAnchor": "Token exchange = hand back BOTH the claim ticket and your locked-away half.",
                    "scene": "In a plain back office the valet slides the melting ice-chip and the cold-blue-flaming jar-half together through a steel mail slot; the slot swallows both with a clack. The flame is the one impossible element. Centered shot.",
                    "caption": "Sliding the ice-chip AND the flaming half together = the app POSTing the Auth Code plus the original Code Verifier to the token endpoint.",
                    "technicalFact": "The app exchanges the Auth Code and the original Code Verifier at the token endpoint over a back channel.",
                    "callbackTo": "locus-pkce-commit",
                },
                {
                    "locusId": "locus-access-token",
                    "locusPhrase": "the teller window with the little bell",
                    "metaphorAnchor": "Access Token = a VIP wristband that lets you in.",
                    "scene": "A gloved hand slides a black wristband across a teller counter; the wristband pulses like a beating heart and has sprouted two small feathered wings. Everything else is ordinary. Centered close-up.",
                    "caption": "The winged, pulsing wristband handed over = the Access Token issued to the app after the PKCE halves match.",
                    "technicalFact": "The server confirms the Verifier hashes to the stored Challenge, then issues an Access Token.",
                    "callbackTo": None,
                },
            ],
        },
        {
            "roomId": "room-vault",
            "roomName": "The High-Roller Vault",
            "conceptTaught": "The app uses the token to read the protected resource.",
            "loci": [
                {
                    "locusId": "locus-resource-request",
                    "locusPhrase": "the round vault door at the end of the hall",
                    "metaphorAnchor": "Using the token = tap the wristband on the reader.",
                    "scene": "The valet taps the winged, pulsing wristband against a round vault door whose keyhole is shaped exactly like the wristband. One impossible element: the winged band. Centered medium shot.",
                    "caption": "Tapping the winged band on the matching keyhole = the app calling the Resource Server with the Access Token as a Bearer credential.",
                    "technicalFact": "The app requests data from the Resource Server, presenting the Access Token as a Bearer token.",
                    "callbackTo": "locus-access-token",
                },
                {
                    "locusId": "locus-resource-response",
                    "locusPhrase": "the open mouth of the vault",
                    "metaphorAnchor": "Getting the data = the vault pays out.",
                    "scene": "The vault door yawns open like a mouth and a single golden coin the size of a manhole cover rolls out and gently flattens the valet against the floor. The giant coin is the one impossible element. Centered wide shot.",
                    "caption": "The manhole-sized coin flattening the valet = the Resource Server validating the token and returning the protected data.",
                    "technicalFact": "The Resource Server validates the token and returns the requested protected data to the app.",
                    "callbackTo": None,
                },
            ],
        },
    ],
}


def _iter_loci(palace):
    for room in palace["rooms"]:
        for locus in room["loci"]:
            yield room, locus


async def render_assets(palace, *, model: str, limit: int) -> None:
    """Render each locus scene to docs/assets/<locusId>.png via the local GPU
    (mode='loci' → surreal-tolerant negative). Cache hits are instant."""
    import os

    os.environ["TUTOR_IMAGES"] = "1"
    from salient_tutor.illustrations import _CACHE_DIR, render as gpu_render

    assets = Path("docs/assets")
    assets.mkdir(parents=True, exist_ok=True)

    done = 0
    for _room, locus in _iter_loci(palace):
        if done >= limit:
            break
        lid = locus["locusId"]
        print(f"  rendering {lid} ({model}) …", flush=True)
        res, err = await gpu_render(f"scene: {locus['scene']}", model=model, mode="loci")
        if res and res.url:
            shutil.copy2(_CACHE_DIR / res.url.split("/")[-1], assets / f"{lid}.png")
            print(f"    ✓ {'cache' if res.cached else 'rendered'} → docs/assets/{lid}.png")
        else:
            print(f"    ✗ {err}")
        done += 1


def build_viewer(palace) -> Path:
    """Emit a self-contained vanilla-JS + D3 recall-viewer (no React)."""
    html = _VIEWER_TEMPLATE.replace("__PALACE_JSON__", json.dumps(palace))
    out = Path("palace_viewer.html")
    out.write_text(html, encoding="utf-8")
    return out


# ── The viewer (vanilla JS + D3; placeholder-replaced, no f-string braces) ─────
_VIEWER_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Memory Palace — Recall Viewer</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  :root {
    --bg: #0d1117; --bg-2: #161b22; --bg-3: #1c2330; --line: #2b3444;
    --ink: #e6edf3; --muted: #8b97a8; --accent: #818cf8; --accent-2: #a78bfa;
    --good: #34d399; --gold: #fbbf24;
  }
  * { box-sizing: border-box; }
  body, html { margin: 0; height: 100%; background: var(--bg); color: var(--ink);
    font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, sans-serif; overflow: hidden; }
  #app { display: flex; height: 100%; }
  #canvas { flex: 1; position: relative; cursor: grab; }
  #canvas:active { cursor: grabbing; }
  #canvas h1 { position: absolute; top: 16px; left: 20px; margin: 0; font-size: 20px;
    color: var(--accent); text-shadow: 0 2px 12px #000; pointer-events: none; max-width: 60%; }
  #canvas .subtitle { position: absolute; top: 44px; left: 20px; color: var(--muted);
    font-size: 13px; pointer-events: none; }
  .node-bg { transition: all .4s ease; }
  .node-img { transition: opacity .4s ease; }
  g.locus { cursor: pointer; }
  g.locus:hover .node-halo { opacity: .9; }
  g.locus.sel .node-halo { opacity: 1; }
  aside { width: 400px; background: var(--bg-2); border-left: 1px solid var(--line);
    display: flex; flex-direction: column; box-shadow: -12px 0 40px #0008; z-index: 5; }
  .modes { display: flex; gap: 6px; padding: 14px; border-bottom: 1px solid var(--line);
    background: var(--bg); position: sticky; top: 0; }
  .modes button { flex: 1; padding: 8px; border-radius: 8px; border: 1px solid var(--line);
    background: var(--bg-3); color: var(--muted); font-weight: 600; cursor: pointer; font-size: 13px; }
  .modes button.on { background: var(--accent); color: #0d1117; border-color: var(--accent); }
  .scroll { overflow-y: auto; padding: 16px; }
  .room { margin-bottom: 22px; }
  .room h3 { margin: 0 0 2px; color: var(--accent-2); font-size: 15px; }
  .room p.concept { margin: 0 0 10px; color: var(--muted); font-size: 12.5px; font-style: italic; }
  .card { border: 1px solid var(--line); border-radius: 12px; padding: 12px; margin-bottom: 10px;
    background: var(--bg-3); transition: border-color .3s, box-shadow .3s; }
  .card.sel { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent), 0 8px 28px #0006; }
  .card.mastered { border-color: var(--gold); box-shadow: 0 0 0 1px var(--gold3, #fbbf2455); }
  .phrase { font-weight: 600; }
  .phrase .loc { color: var(--muted); font-weight: 400; }
  .badge { float: right; font-size: 11px; padding: 1px 8px; border-radius: 999px;
    background: var(--bg); color: var(--muted); border: 1px solid var(--line); }
  .badge.MASTERED { color: var(--gold); border-color: var(--gold); }
  .badge.REVEALED { color: var(--good); border-color: var(--good); }
  .hint { margin: 10px 0 0; padding: 8px 10px; border-left: 2px solid var(--accent-2);
    background: #a78bfa14; color: #cbb8f6; font-size: 13px; border-radius: 0 6px 6px 0; }
  .reveal { margin-top: 10px; }
  .reveal img { width: 100%; border-radius: 8px; display: block; background: #000; }
  .reveal .cap { margin: 8px 0 0; font-size: 13px; color: var(--ink); }
  .reveal .fact { margin: 8px 0 0; font-size: 13px; color: var(--good); font-weight: 600; }
  .cb { display: inline-block; margin-top: 8px; font-size: 12px; color: var(--accent);
    cursor: pointer; border: 1px dashed var(--accent); border-radius: 999px; padding: 1px 9px; }
  .actions { margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap; }
  .actions button { flex: 1; min-width: 62px; padding: 7px 4px; border-radius: 8px; cursor: pointer;
    border: 1px solid var(--line); background: var(--bg); color: var(--ink); font-size: 12.5px; font-weight: 600; }
  .actions .ghost { color: var(--muted); }
  .actions .g-again { border-color: #f87171; color: #f87171; }
  .actions .g-good { border-color: var(--good); color: var(--good); }
  .lb { margin-top: 8px; }
  .note { padding: 10px 16px; color: var(--muted); font-size: 11.5px; border-top: 1px solid var(--line); }
</style>
</head>
<body>
<div id="app">
  <div id="canvas">
    <h1></h1>
    <div class="subtitle"></div>
    <svg width="100%" height="100%"></svg>
  </div>
  <aside>
    <div class="modes">
      <button data-mode="lightbox" class="on">Lightbox</button>
      <button data-mode="fly">Fly-to-Zoom</button>
    </div>
    <div class="scroll" id="rooms"></div>
    <div class="note">Grades persist to localStorage here; in the app they call
      <code>record_review()</code> → the SM-2 gradebook (topic <code>loci:&lt;palace&gt;/&lt;locus&gt;</code>).</div>
  </aside>
</div>
<script>
const PALACE = __PALACE_JSON__;
const KEY = "palace." + PALACE.palaceId;
const STATES = ["HIDDEN","HINTED","ATTEMPTED","REVEALED","MASTERED"];
const CELL = 300, GAP = 60, PAD = 120;

const store = (() => {
  let s = {}; try { s = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (_) {}
  return {
    get: id => s[id] || { state: "HIDDEN", streak: 0 },
    set: (id, v) => { s[id] = v; try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (_) {} },
  };
})();

const loci = [];
PALACE.rooms.forEach(r => r.loci.forEach(l => loci.push({ room: r, ...l })));
loci.forEach((l, i) => { l.x = PAD + i * (CELL + GAP); l.y = PAD; });
const byId = Object.fromEntries(loci.map(l => [l.locusId, l]));

let selected = null, mode = "lightbox";
const svg = d3.select("#canvas svg");
const zoomG = svg.append("g");
const zoom = d3.zoom().scaleExtent([0.15, 5]).on("zoom", e => zoomG.attr("transform", e.transform));
svg.call(zoom).on("click", () => select(null));
d3.select("#canvas h1").text(PALACE.palaceTheme);
d3.select("#canvas .subtitle").text(PALACE.topic);

// ── Canvas nodes ──────────────────────────────────────────────────────────
const node = zoomG.selectAll("g.locus").data(loci).enter().append("g")
  .attr("class", "locus").attr("id", d => "n-" + d.locusId)
  .attr("transform", d => `translate(${d.x},${d.y})`)
  .on("click", (e, d) => { e.stopPropagation(); select(d.locusId); });
node.append("rect").attr("class", "node-halo").attr("x", -8).attr("y", -8)
  .attr("width", CELL + 16).attr("height", CELL + 16).attr("rx", 26)
  .attr("fill", "none").attr("stroke", "#818cf8").attr("stroke-width", 3).attr("opacity", 0);
node.append("rect").attr("class", "node-bg").attr("width", CELL).attr("height", CELL)
  .attr("rx", 24).attr("fill", "#1c2330");
node.append("image").attr("class", "node-img").attr("href", d => `docs/assets/${d.locusId}.png`)
  .attr("width", CELL).attr("height", CELL).attr("preserveAspectRatio", "xMidYMid slice")
  .attr("clip-path", "inset(0 round 24px)");
node.append("text").attr("class", "node-cap").attr("x", CELL / 2).attr("y", CELL + 26)
  .attr("text-anchor", "middle").attr("fill", "#8b97a8").attr("font-size", 15)
  .text(d => d.locusPhrase);

function applyMode() {
  const lb = mode === "lightbox";
  d3.selectAll("button[data-mode]").classed("on", function () { return this.dataset.mode === mode; });
  node.select(".node-img").style("opacity", lb ? 0 : 1);
  node.select(".node-bg")
    .attr("fill", lb ? "#818cf8" : "#1c2330")
    .attr("width", lb ? 70 : CELL).attr("height", lb ? 70 : CELL)
    .attr("x", lb ? CELL / 2 - 35 : 0).attr("y", lb ? CELL / 2 - 35 : 0)
    .attr("rx", lb ? 35 : 24);
}
d3.selectAll("button[data-mode]").on("click", function () { mode = this.dataset.mode; applyMode(); });

function flyTo(d) {
  const w = document.getElementById("canvas").clientWidth, h = document.getElementById("canvas").clientHeight;
  const t = d3.zoomIdentity.translate(w / 2, h / 2).scale(2.6).translate(-d.x - CELL / 2, -d.y - CELL / 2);
  svg.transition().duration(1000).call(zoom.transform, t);
}
function fitAll() {
  const total = PAD * 2 + loci.length * (CELL + GAP);
  const w = document.getElementById("canvas").clientWidth || 1200;
  svg.transition().duration(600).call(zoom.transform, d3.zoomIdentity.scale(Math.min(0.9, w / total)));
}

// ── Sidebar recall ladder ───────────────────────────────────────────────────
function select(id) {
  selected = id;
  node.classed("sel", d => d.locusId === id);
  d3.selectAll(".card").classed("sel", function () { return this.dataset.id === id; });
  if (id) {
    const card = document.querySelector(`.card[data-id="${id}"]`);
    if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
    if (mode === "fly") flyTo(byId[id]);
  }
}

function grade(l, g) {
  const st = store.get(l.locusId);
  const good = g === "good" || g === "easy";
  const streak = good ? st.streak + 1 : 0;
  const state = streak >= 3 ? "MASTERED" : "REVEALED";
  store.set(l.locusId, { state, streak });
  render();
  select(l.locusId);
}

function render() {
  const root = d3.select("#rooms").html("");
  PALACE.rooms.forEach(room => {
    const box = root.append("div").attr("class", "room");
    box.append("h3").text(room.roomName);
    box.append("p").attr("class", "concept").text(room.conceptTaught);
    room.loci.forEach(l => {
      const st = store.get(l.locusId);
      const card = box.append("div").attr("class", "card " + (st.state === "MASTERED" ? "mastered" : ""))
        .attr("data-id", l.locusId).on("click", (e) => { e.stopPropagation(); select(l.locusId); });
      const head = card.append("div").attr("class", "phrase");
      head.append("span").attr("class", "badge " + st.state).text(st.state.toLowerCase());
      head.append("span").html(`<span class="loc">at</span> ${l.locusPhrase}`);

      // Ladder controls
      const showHint = st.state === "HINTED" || st.state === "ATTEMPTED";
      const revealed = st.state === "REVEALED" || st.state === "MASTERED";
      if (showHint) card.append("div").attr("class", "hint").html("💡 " + l.metaphorAnchor);

      if (revealed) {
        const rv = card.append("div").attr("class", "reveal");
        rv.append("img").attr("src", `docs/assets/${l.locusId}.png`).attr("alt", l.locusPhrase);
        rv.append("p").attr("class", "cap").text(l.caption);
        rv.append("p").attr("class", "fact").text("✓ " + l.technicalFact);
        if (l.callbackTo && byId[l.callbackTo]) {
          rv.append("span").attr("class", "cb").text("↩ callback: " + byId[l.callbackTo].locusPhrase)
            .on("click", (e) => { e.stopPropagation(); select(l.callbackTo); });
        }
        const act = rv.append("div").attr("class", "actions");
        [["again", "Again"], ["hard", "Hard"], ["good", "Good"], ["easy", "Easy"]].forEach(([g, label]) => {
          act.append("button").attr("class", g === "again" ? "g-again" : g === "good" || g === "easy" ? "g-good" : "ghost")
            .text(label).on("click", (e) => { e.stopPropagation(); grade(l, g); });
        });
      } else {
        const act = card.append("div").attr("class", "actions lb");
        if (!showHint) act.append("button").attr("class", "ghost").text("💡 Hint")
          .on("click", (e) => { e.stopPropagation(); store.set(l.locusId, { ...st, state: "HINTED" }); render(); select(l.locusId); });
        act.append("button").attr("class", "g-good").text("Reveal answer")
          .on("click", (e) => { e.stopPropagation(); store.set(l.locusId, { ...st, state: "REVEALED" }); render(); select(l.locusId); });
      }
    });
  });
}

render();
applyMode();
setTimeout(fitAll, 100);
</script>
</body>
</html>
"""


async def main() -> None:
    argv = sys.argv[1:]
    limit = next((int(a.split("=")[1]) for a in argv if a.startswith("--limit=")), 10_000)
    model = "flux-schnell" if "--fast" in argv else "flux-dev"

    print(f"Palace: {PALACE['palaceId']} — {sum(len(r['loci']) for r in PALACE['rooms'])} loci")
    if "--local-gpu" in argv:
        print(f"Rendering on local GPU (ai.home), model={model}, mode=loci, limit={limit}:")
        await render_assets(PALACE, model=model, limit=limit)
    else:
        print("(no --local-gpu: rebuilding viewer HTML only)")

    out = build_viewer(PALACE)
    print(f"\n✅ Done → open {out.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
