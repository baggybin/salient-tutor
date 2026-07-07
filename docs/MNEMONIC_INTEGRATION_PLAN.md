# Mnemonic Integration Plan (vetted)

How to bake the memory-palace playground (`tools/build_memory_palace.py`,
`docs/MNEMONIC_BIBLE.md`) into the real app. This supersedes the original naive
4-step plan: that plan was written without sight of the codebase and
double-implemented things the app already has. The plan below is the
**de-conflicted** version, cross-checked by Fable, Gemini 3.1 Pro, and a
2-model council (all converged).

## What the app ALREADY has (do not duplicate)
- **A real SRS.** `salient_core.tutor.schedule` (SM-2) + `TutorDaemon.record_review(topic, grade)` writes `learner_review_state` into the KG (`learner:op`); the skill-map rail already buckets topics into due/strong/weak/mastered with recall-odds + a review-load forecast. **This is the source of truth** — the Bible's localStorage FSM would fragment it.
- **A mature imagery skill** (`prompts/skills/image_authoring.md`, council-derived). It is *more* cognitively correct than the Bible on the key point: the von Restorff isolation effect needs **exactly ONE odd element on the target against a mundane scene** — "if everything is surreal, nothing is distinctive" — and **mild humor > fear/disgust** (high arousal narrows attention onto the wrong details). So we REJECT the Bible's "crank absurdity to 11 / disgust / taboo / sexual" and keep the disciplined rule.
- **A per-image render seam** (`illustrations.render`): `ImageSpec{scene,caption,width,height,mode}`, modes `mnemonic/loci/labeled`, server-owned style + negative, deterministic content-addressed PNG cache, one-GPU semaphore, opt-in `TUTOR_IMAGES=1`. Fence: ```` ```image <mode> ````.
- A vanilla-JS SPA (`web/static/js/tutor.js`) + `app.css` — **no React**.

## Empirical findings from the playground (real ai.home GPU renders)
- **Object / material / scale bizarreness renders cleanly and memorably** (a glowing glass jar with cold blue flame swallowing a ticket; a giant coin). **Anatomical** impossibilities (a "swollen giant hand") render poorly/ambiguously — prefer object-scale violations in scenes and in the skill.
- `mode:"loci"` + **no in-image text** eliminated the gibberish-text failure (`flux` was rendering "permistion lipe" garbage into mnemonic images). The mapping belongs in the **caption**, never painted into the image.

## The de-conflicted design

### Wire format — one `palace` fence, frontend fans out to N `/api/image`
The tutor emits a single ```` ```palace ```` JSON block; the frontend expands it into N normal `POST /api/image` calls (one cached PNG per locus), reusing the existing render+cache path verbatim. (Not a server-side fan-out endpoint — that holds one HTTP request open behind the GPU semaphore for M×N renders.) Schema:

```json
{
  "version": 1, "palaceId": "kebab-id", "palaceTheme": "...", "topic": "concept the learner named",
  "rooms": [{
    "roomId": "r1", "roomName": "...", "conceptTaught": "MUST exact-match an existing gradebook topic",
    "loci": [{
      "locusId": "r1.l1",
      "locusPhrase": "the mundane, verbatim-reused anchor",
      "metaphorAnchor": "the abstraction bridge — pre-reveal HINT",
      "scene": "ONE bizarre element on the target, mundane elsewhere, no text",
      "caption": "the element->fact MAPPING — post-reveal",
      "technicalFact": "the literal fact",
      "callbackTo": "optional earlier locusId (scene visually quotes that motif)"
    }]
  }]
}
```
Deleted from the Bible's schema: `boundingBox` (no D3 fly-to needed — CSS handles it), `arousalChannel` (it's a *constraint* in the skill, not per-locus data — storing it invites violating the one-element rule), and `visualDescription` is renamed **`scene`** (it IS `ImageSpec.scene`). Only render-affecting fields (`scene`, `caption`, `mode:"loci"`) cross `/api/image` — hint/fact/callback must NOT enter the sha256 cache key.

### `metaphorAnchor` vs `caption` — distinct points on the recall ladder
- **Prompt:** show `locusPhrase` only ("the coat-check counter — what's here?").
- **Hint** (on miss): `metaphorAnchor` (grade caps at "hard" once shown).
- **Reveal:** image + `caption` (the mapping) + `technicalFact` + grade buttons.
Collapsing anchor into caption gives the answer away on the hint step.

### Negative prompt — mode-keyed (DONE)
`illustrations.py` now has `_NEGATIVE_LOCI` (drops "ugly, deformed" so one impossible object survives the sampler; keeps text/quality bans + "extra fingers, mutated hands" to kill true defects). The single-bizarre-element discipline is enforced by the **prompt**, not the negative. The negative is part of the content-address, so this re-keys `loci` images cleanly (no stale serving).

### SRS — loci are SM-2 topics; concept mastery is READ-TIME derived (council Option C)
- Each locus grade → `record_review("loci:{palaceId}/{locusId}", grade)`. `record_review` already takes an arbitrary topic ⇒ ~zero backend change.
- **One-way ownership** (makes double-recording structurally impossible): the palace flow writes ONLY `loci:*`; the concept topic's SM-2 state stays owned exclusively by `quiz()/grade_quiz()`. Concept "palace mastery" is a **read-time `min` over the concept's live loci** (via a `locus —teaches→ conceptTaught` KG edge), shown as a *secondary badge* — never written into the concept's `learner_review_state`. (Do NOT intercept concept reviews and reroute to loci — a quiz is free recall of the concept, a locus is cued recall of one image; different units.)
- **Rail hygiene:** filter `topic.startswith("loci:")` out of the default buckets (centralize the predicate); concept rows get a `🏛 3/12 loci weak → [enter palace]` badge; the forecast shows loci as a separate stacked "palace load" segment.
- **Longevity:** reserve the `loci:` namespace now; palace regeneration = archive its `loci:*` keys (reset, not migration — the image *is* the card). Constrain `conceptTaught` to an existing gradebook key to avoid phantom-topic drift.
- **Highest risk — stale-min drag:** an abandoned palace's overdue loci pin a concept badge at "weak" forever. Mitigation from day one: drop a locus from the roll-up once overdue > ~2× its interval (or its palace is archived); make the badge explanatory + one click into the palace.

## Module boundaries
| Where | What |
|---|---|
| `illustrations.py` | ✅ mode-keyed negative (done). Nothing else — it renders one spec. |
| **new** `salient_core/tutor/palace.py` | schema validation, `locus_topic()`, persist/load palace doc, `palace_state(id)` joining loci × `learner_review_state`. No HTTP/render. |
| `daemon.py` / `web.py` | thin `POST /api/review {topic,grade}` (palace grades ride the existing `record_review`), `POST /api/palace` (validate+persist), `GET /api/palace/{id}/state`. Delegate SM-2/schema to `palace.py`. |
| **new** `prompts/skills/palace_authoring.md` | extends `image_authoring.md` (per-locus scene rules unchanged); adds `metaphorAnchor` required, `callbackTo` references an earlier locus, `conceptTaught` must match a gradebook topic. Prefer object/scale bizarreness over anatomical. |
| `tutor.js` | `lang==="palace"` handler: parse JSON → room sections → per-locus recall-ladder card (reuse `renderImage` with `mode:"loci"`); grade → `POST /api/review` with `locus_topic`; `callbackTo` → chip that scrolls+highlights. Plain JS + existing CSS. |

The vanilla-JS + D3 recall viewer in `tools/build_memory_palace.py` is the **reference implementation** for the `tutor.js` port.

## Shippable increments
1. **Skill + `tutor.js` palace handler + `illustrations.py` negative (negative DONE).** Tutor emits a palace; M rooms × N cached loci; recall ladder with `metaphorAnchor` hints + callback links; grades flow into the EXISTING SM-2 gradebook via `loci:*` topics. Palace lives in the transcript (the part that must persist — SRS state — already persists in the KG).
2. **`palace.py` + the review/palace endpoints:** palace persists; `GET /state` shows mastered/due badges on revisit; rail rolls loci→concept via the KG edge with the stale-min guard.
3. **Viewer polish:** room minimap, mastered-room dimming, CSS fly-to. Last — steal ideas (not code) from the prototype.
