# SKILL — Authoring a memory palace

How to build a **method-of-loci memory palace**: a spatial walk of linked loci
that encodes a *multi-step* concept (a protocol, a pipeline, an ordered
procedure) so the learner can re-walk it from memory. This EXTENDS
`image_authoring.md` — every per-locus scene obeys those rules unchanged. This
file adds the palace structure, the recall ladder, and the wire format.

## When to build a palace (vs a single image)

A palace is worth it only when the content is an **ordered, multi-step whole**
the learner must recall *in sequence* — a handshake, an auth flow, a kill chain,
a lifecycle. 8–15 loci across 3–5 rooms. For a single fact, use one ```` ```image ````;
for edges/ordering that must be *read precisely*, use a diagram (the 3 gates in
`image_authoring.md` still apply per locus).

## The wire format — one ```` ```palace ```` fence, raw JSON

Emit ONE fenced ```` ```palace ```` block whose body is raw JSON (no prose, no
markdown inside). The client expands it into one cached image per locus and
renders the recall ladder; grades flow to the SM-2 gradebook.

````
```palace
{
  "version": 1,
  "palaceId": "kebab-unique-id",
  "palaceTheme": "one vivid, COHERENT environment (a manor, a casino, a ship)",
  "topic": "the concept the learner named — must match their gradebook topic",
  "rooms": [
    {
      "roomId": "r1",
      "roomName": "plain room name",
      "conceptTaught": "the sub-concept this room teaches",
      "loci": [
        {
          "locusId": "r1-l1",
          "locusPhrase": "the mundane fixed anchor, reused VERBATIM every visit",
          "metaphorAnchor": "the concrete metaphor / abstraction bridge (the HINT)",
          "scene": "the ```image loci scene body — ONE bizarre element, no text",
          "caption": "the element -> fact MAPPING (shown AFTER recall)",
          "technicalFact": "the literal fact being encoded",
          "callbackTo": "an earlier locusId this scene visually quotes, or omit"
        }
      ]
    }
  ]
}
```
````

## Field rules (this is where a palace differs from a lone image)

- **`locusPhrase`** — the *place*, kept mundane and written **identically** on
  every visit ("the coat-check counter beside the podium"). It is the retrieval
  cue; only the placed item carries the bizarreness. Never park two concepts at
  one locus; never move a concept between loci.
- **`metaphorAnchor`** — the concrete metaphor for the (often abstract) fact
  ("PKCE = tear a ticket in half, lock your half away"). It is the **pre-reveal
  HINT**: shown only after the learner struggles. So it must *point* without
  giving the answer — it is NOT the mapping.
- **`scene`** — authored exactly per `image_authoring.md` (rendered in `loci`
  mode): one focal subject, one transitive action mid-doing, **exactly ONE**
  impossible element ON the target, mundane elsewhere, **zero in-image text**.
  PREFER object / scale / material violations (a pen grown to pool-cue size, a
  ticket sealed in a jar of cold blue flame, a winged pulsing wristband) —
  diffusion renders these cleanly. AVOID anatomical impossibilities (giant
  hands, extra limbs); they render as mush. Apply the **Vividness** rule from
  `image_authoring.md` — but here it's load-bearing twice: the `locusPhrase`
  stays plain AND verbatim, so the whole vividness budget spends on the placed
  item, never the locus.
- **`caption`** — the **mapping**, element → fact, shown *after* the learner
  attempts recall ("the melting ice-chip in the tube = the short-lived
  Authorization Code"). Not a description of the picture.
- **`technicalFact`** — the plain fact, revealed with the caption.
- **`callbackTo`** — optionally name an earlier `locusId`; the scene must then
  *visually quote* that locus's bizarre item (the flaming half returns, the
  winged band reappears). Callbacks fight the serial-position effect — they knit
  a recognition network so middle loci aren't lost. Use ≥1 per palace.

## Palace-level discipline

- **`palaceTheme` is ONE coherent place.** The rooms are a walk through it in a
  fixed order — the spatial sequence IS the ordering of the steps.
- **Serial-position:** put the densest/most-important loci at the FIRST and LAST
  positions; make the MIDDLE loci the most vivid (they're the ones lost).
- **`conceptTaught` / `topic` must match an existing gradebook topic** (what the
  learner would name), so palace mastery rolls up into the skill map. Don't
  invent a near-duplicate spelling.
- **Budget the bizarreness across the whole walk** — one striking element per
  locus, not a surreal blur. If every room screams, nothing is distinctive.

## Checklist — before emitting a ```` ```palace ````

```
[ ] Content is a genuinely ORDERED, multi-step whole (else use ```image / a diagram)
[ ] ONE coherent palaceTheme; rooms walk it in step order
[ ] 8–15 loci; each locus = one fact, one locusPhrase (mundane, verbatim)
[ ] Each scene passes image_authoring: one subject, one transitive action,
    exactly ONE bizarre element (object/scale/material, NOT anatomical), no text
[ ] metaphorAnchor points without giving the answer (it's the hint)
[ ] caption states the element->fact MAPPING (shown post-recall)
[ ] ≥1 callbackTo, whose scene visually quotes the referenced locus
[ ] densest loci at first/last; middle loci most vivid
[ ] conceptTaught/topic match the learner's gradebook topic
[ ] raw JSON only inside the fence — no prose, no nested markdown
```
