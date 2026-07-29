# SKILL — Authoring a keyword/decomposition image

How to encode **one abstract term** as an ImageSpec for the `/api/image`
pipeline: decompose the term into concrete components, then compose those
components into ONE bizarre story image whose caption states the mapping. This
is the 说文解字 move (decompose + story) and generalizes the Keyword Method —
the "keyword" is the term's own roots/components instead of a soundalike. It
EXTENDS `image_authoring.md` — every rule there applies unchanged, including
the **exactly ONE bizarre element** rule.

## When to use it

Only for **opaque terms** — crypto-, -ectomy, ortho-, Kerberos, eigen- — whose
label gives the learner no hook. If the term is already transparent
("firewall"), skip decomposition and go straight to `image_authoring.md`. If
the term has no honest decomposition, fall back to a SOUNDALIKE keyword
("Kerberos" → a three-headed dog) and encode that instead.

## The pipeline (three steps, in order)

1. **DECOMPOSE.** Split the term into 2–4 concrete components — Greek/Latin
   roots, morphemes, or a verified soundalike per part. **Never invent folk
   etymology**: a plausible-but-false split encodes a false fact. If you can't
   verify the split, say so and use a soundalike.
2. **CONCRETIZE.** Give each component one concrete, paintable stand-in
   (kryptós "hidden" → a hooded cloak; gráphein "write" → a quill). Keep each
   stand-in **stable** for the whole session — once a root has a stand-in,
   reuse it for every term sharing that root.
3. **COMPOSE.** Build ONE scene where the component stand-ins *interact*
   (transitive verb, mid-action) to act out the modern meaning — subject-first,
   one focal subject, and **exactly ONE bizarre element ON the target**
   (object/scale/material violation, not anatomical), mundane elsewhere,
   zero in-image text. Components merely co-located do not encode.

## The wire format — one ```` ```image ```` fence (mode `mnemonic`)

Emit exactly what `image_authoring.md` specifies; the server parses it into an
`ImageSpec` (`scene`, `caption`, `width`, `height`, `mode` — see
`src/salient_tutor/illustrations.py`). First line is `caption: ...` stating
the **mapping** (component → meaning), then a 70–110-word present-tense scene
paragraph, subject-first. Example:

````
```image mnemonic
caption: Cryptography = kryptós ("hidden") + gráphein ("to write") — the hooded scribe writing in invisible ink is secret writing.
A hooded scribe in a plain gray cloak dips a white goose quill into an inkwell and writes a letter that vanishes word by word the moment the quill lifts, the fresh strokes gone as if never written. The scribe's cloak has swollen to the size of a tent, hiding the whole desk under its folds. A bare wooden stool and a plain stone floor, nothing else. Centered close-up.
```
````

Recall path to state after the image: **term → components → scene → meaning.**

## The 歇后语 template — scene first, punchline after

When the term resists decomposition and even a soundalike is strained, use the
two-part allegorical (歇后语) pattern as the metaphorAnchor: find a concrete
mini-scene whose PHYSICS enact the meaning, then attach the meaning as the
punchline — "a mud bodhisattva crosses the river — it can't even save itself".
The scene is the pre-reveal hint (it points without stating the answer); the
punchline is the mapping. Same discipline as above: one scene, one bizarre
element ON the target, caption states scene → meaning. The scene must *enact*
the fact, not decorate it — a vivid scene that merely co-occurs with the
meaning cues nothing.

## Checklist — before emitting

```
[ ] Term is genuinely OPAQUE (else skip); decomposition verified, not folk etymology
[ ] 2–4 components, each with ONE stable concrete stand-in
[ ] Stand-ins INTERACT (transitive verb, mid-action) — not co-located
[ ] Exactly ONE bizarre element, ON the target, object/scale/material (NOT anatomical)
[ ] One focal subject; mundane elsewhere; zero in-image text; zero style words
[ ] caption states the component->meaning MAPPING; scene 70–110 words, present tense
[ ] Recall path (term -> components -> scene -> meaning) stated after the fence
```
