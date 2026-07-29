# SKILL — Authoring learning images

How to write an ` ```image ` fence that actually helps a learner remember or
understand. This is the full reference; the tutor prompt carries only the
compressed always-on version. The **server** owns all style, palette, model
choice, and seeding — you describe a *scene*, never a look. (Derived from a
multi-model council synthesis on the pedagogy of instructional imagery.)

The invariant behind every rule: **every pixel is a memory write.** If an
element doesn't encode a target fact, it's noise — cut it. Test each image:
*could the learner reconstruct the fact from the image + caption alone?*

---

## Modes

Pick one; it is the fence info-string (` ```image <mode> `). The server routes
model + text-policy from it — you never name a model.

| Mode | Use for | Text in image? |
|---|---|---|
| `mnemonic` | encode ONE fact as an interacting scene | no |
| `loci` | place one item at one fixed memory-palace locus | no |
| `labeled` | depict a THING with ≤5 short name-callouts | yes (short names only) |

Default is `mnemonic` if the info-string is omitted.

## The 3 gates — is an image even right? (stop at the first match)

1. **Topology gate.** If correctness depends on *edges* — which arrow connects
   to which node, ordering, hierarchy, state transitions, sequence — use a
   **deterministic diagram engine** (mermaid/dot/d2), never diffusion. Diffusion
   cannot guarantee arrow endpoints, even qwen. Flows, graphs, trees, state
   machines, sequence diagrams, timelines → diagram.
2. **Text-precision gate.** If any text is *verbatim-critical* (code,
   identifiers, protocol values, numbers-as-data, equations), or the scene needs
   >5 labels or any label >3 words → **diagram**. Qwen's text is good, not
   guaranteed; a mangled label in a mnemonic is harmless, a mangled label in
   reference material is misinformation. **Qwen labels are names, never data.**
3. **Depiction gate.** If it's a *picture of a thing* (object, cutaway, spatial
   arrangement) with ≤5 short callouts naming visible parts → `labeled`.
   Everything else → `mnemonic`/`loci`, or no image at all.

Two cross-checks: **"delete the labels — does the picture still teach?"** (yes →
`labeled`; if the labels *are* the lesson → diagram). And **read vs. trace** (if
the learner must trace paths or compare precise structure → diagram).

## Pedagogy → concrete rules

- **Dual coding**: the image must encode the *same proposition* as the words,
  not decorate them. Decorative "seductive detail" measurably hurts recall.
- **Interaction beats co-location** (highest-leverage rule): elements must *act
  on each other*. "A bear strangling a router" is retrievable; "a bear next to a
  router" is not. Require a **transitive verb, mid-action**.
- **Bizarreness (von Restorff)**: exactly ONE odd element, sitting **on the
  target concept**, against an otherwise mundane scene. A weird background is
  noise; if everything is surreal, nothing is distinctive. Budget it across the
  session too.
- **Vividness — rich on the ONE thing, plain everywhere else**: pour sensory,
  material, scale, weight, motion, and implied-sound detail into the focal
  subject and its single action ("dented brass knuckle", "so heavy it leans
  back to hold it"); leave every other element deliberately generic ("a plain
  corridor", "a bare desk"). Colour and texture are allowed **only as properties
  bound to a named object** ("rust-orange stopwatch") — never as free-floating
  look words ("warm orange tones"), and never lighting/mood/palette/medium/
  artist/render-quality terms (the server owns those). The best vivid detail
  *re-encodes the fact* ("its second hand ticking in ever-widening sweeps" =
  the interval growing), not just decorates. This prevents the three ways "be
  more descriptive" fails: clutter (new elements = new memory traces competing
  with the target), seductive detail (a decorated background that steals
  encoding), and style leakage (aesthetic words that fight the server's brand
  wrap).
- **Emotional salience**: mild surprise/humor/gentle absurdity > fear/disgust
  (high arousal narrows attention onto the wrong details). Affect attaches to
  the concept (a cracked shield ⇒ a broken invariant).
- **Cognitive load**: 3–5 meaningful elements, one focal subject, one action.
- **Concreteness**: reify abstractions into paintable stand-ins ("latency" → "a
  snail carrying an envelope"), and keep the symbol **stable** across the
  session — once "regularization = tightening strap", never switch it.
- **Loci spatial consistency**: the *locus* stays mundane and its phrase is
  reused **verbatim** across cards; only the *placed item* carries bizarreness.
  Never park two concepts in one locus; never move a concept between loci.
- **Spatial layout can encode meaning**: left⇒before, container⇒subset,
  clockwise⇒cycle — use deliberately, never contradicting the concept.
- **Caption = the mapping**, not a description ("the doubling gaps = exponential
  backoff"). If the mapping can't be stated in one line, the image won't cue.

## Fill-in template (fill the slots, then emit as prose)

Flux and qwen are trained on flowing captions, not key:value soup — so decide
each slot, then **render them as one 40–80-word present-tense paragraph**,
subject-first.

```
SUBJECT:  one concrete focal noun — the concept's stand-in
ACTION:   one transitive verb, mid-doing — subject acts ON something
OBJECTS:  ≤2–3 supporting props, each mapped to a content element
SETTING:  mundane, minimal; loci: the fixed locus phrase, VERBATIM
TWIST:    the one bizarre/salient element, on the target (exactly one)
FRAMING:  one phrase — "centered close-up" | "wide shot" | "cutaway view"
labeled +LABELS: ≤5, each an exact "quoted string" ≤3 words, a NAME not data,
         placed ("a label reading \"header\" above the first segment")
→ 70–110 words, present tense, subject-first, counts spelled out in words,
  ZERO style/color/lighting/medium/artist words (the server owns those).
  The word budget grew but the ELEMENT budget did not (still 3–5): every word
  past ~60 must land on the focal subject or its action. If a sentence can be
  deleted without weakening the element→fact mapping, it's decoration — cut it.
```

## Checklist — apply before emitting any ` ```image `

```
MODE picked (mnemonic | loci | labeled) and 3 gates passed
[ ] One concept per image; ≤1 image per reply
[ ] One focal subject doing ONE transitive action, mid-doing
[ ] ≤5 elements; every element maps to a content element; cut the rest
[ ] Exactly one bizarre/salient element, ON the target (humor > fear);
    loci: bizarreness only in the PLACED ITEM — locus phrase reused VERBATIM
[ ] All nouns concrete, specific, paintable; abstractions reified;
    symbol-for-concept stable across the session
[ ] Counts that matter spelled out in words
[ ] Spatial layout encodes meaning where possible, never contradicts it
[ ] 70–110 words, present tense, subject-first
[ ] Vividness audit: every adjective/adverb attaches to the focal subject or
    its one action — no background noun gained detail, no new noun appeared,
    and no detail exists that doesn't restate the fact
[ ] ZERO style/color/lighting/medium/artist words — server owns style
[ ] labeled: every label an exact "quoted string" ≤3 words, a NAME not data,
    with placement, against an uncluttered background
[ ] Caption states the MAPPING (element → concept), not the scene
[ ] Learner could reconstruct the fact from image + caption alone
```

## Worked examples

**Mnemonic — exponential backoff (retries double their wait):**

````
```image mnemonic
caption: Each retry waits twice as long — the doubling gaps are exponential backoff, the giant stopwatch is the wait.
A small round robot raps its dented brass knuckle against an enormous sealed vault door, gets no answer, and steps backward. Behind it, four of its own footprints press deep into gray dust, each gap between them twice as wide as the last — the first a hand-span, the fourth so wide it runs toward the horizon. The robot hugs a stopwatch grown to the size of a shield, so heavy it leans back under the weight, its second hand ticking in slow, ever-widening sweeps. The corridor and vault door are plain and bare. Centered wide shot.
```
````
~95 words, still four elements (robot, door, footprints, stopwatch) and one
transitive action (*raps*); the vivid detail lands only on the focal
subject/action and even *re-encodes the fact* ("ever-widening sweeps",
"leans back under the weight" = the interval growing, waiting costing more each
round), while the setting is explicitly declared mundane ("plain and bare").
Counts spelled out; "brass"/"gray"/"dust" are object-bound, zero style words.

**Loci — palace "the kitchen", locus 2 = the refrigerator; item = certificate validation (TLS handshake step 2):**

````
```image loci
caption: Locus 2 (refrigerator): the notary owl stamping the sealed scroll = the server's certificate being validated.
The kitchen refrigerator, its door wide open. Inside, instead of food, a single giant wax-sealed scroll sits on the middle shelf, and a stern notary owl perched on the butter compartment stamps it with an oversized rubber stamp. Everything else in the kitchen is ordinary. Centered medium shot on the open refrigerator.
```
````
The locus phrase "the kitchen refrigerator, its door wide open" must appear
identically on every visit to this locus; only the placed item and its one
absurdity change.

**Labeled (informational, qwen) — structure of a JWT:**

````
```image labeled
caption: A JWT is three dot-separated parts — header, payload, signature; only the signature makes it tamper-evident.
A cutaway of a single horizontal token shaped like a train of three connected capsule segments. The first segment holds a gear, with a small label reading "header" above it. The middle, largest segment holds an open envelope, with a label reading "payload" above it. The last segment holds a wax seal, with a label reading "signature" above it. Thin dots separate the three segments. Centered wide shot, plain background.
```
````
Passes all three gates: no meaningful edges, three one-word labels that are names
not data, and the visual form (three-segment train, dots between) *is* the
content — delete the labels and the picture still teaches the shape. The same
concept with real base64 contents would fail gate 2 → use a code block instead.
