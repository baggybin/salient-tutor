# SKILL — Authoring a mnemonic verse

How to build a **rhymed formula verse** (口诀-style chant): a short rhymed,
metered verse that encodes an *ordered* body of facts (a table, a formula set,
a procedure) so the cadence forces the items back out in order. Rhythm and
rhyme are retrieval constraints — each line's meter and end-sound narrow the
candidate words, so partial recall completes itself. This is the classical
九九歌 (nine-nines chant) move; it EXTENDS `image_authoring.md` — any
per-line scene obeys those rules unchanged.

## When a verse is worth it

Only when the content is an **ordered sequence that must come out verbatim** —
a multiplication-style table, a safety drill, a formula chain — and is short
enough to chant (≤ ~30 items). For a single fact, use one ```` ```image ````;
for edges/ordering that must be *read precisely*, use a diagram. If the
material has real logic to reason from, teach the logic instead.

## The rules

- **Meter first, then rhyme.** Fix the syllable/beats-per-line count BEFORE
  writing content. The beat is the scaffold; rhyme is the lock. Say every
  line aloud while drafting — if it doesn't chant, it won't stick.
- **Three-beat chunking.** Prefer triplets (three syllables, words, or beats
  per group) for list-like content — the 三字经 frame ("Stop, Drop, and
  Roll"). A fixed 3-beat frame makes each chunk self-checking: a malformed
  chunk is immediately audible.
- **One vivid concrete image per line.** Each line names a thing you can
  picture doing something — not a category, not a concept. The image carries
  the fact; the cadence carries the order.
- **Ban abstract filler words.** No "aspect", "factor", "process", "system",
  "various". If a line survives deleting its nouns, it was filler.
- **Fact over rhyme.** Never distort a fact to fit the meter. If the honest
  item won't scan, change the meter or split the line — a corrupted fact in
  perfect rhyme is worse than none.
- **Meaning stays attached.** The classic failure is the chant that decouples
  from the facts. Close every verse with the mapping: which line encodes
  which fact.

## The wire format — plain text, three parts

```
<the verse, one line per chunk, no commentary interleaved>

MAPPING: line N -> the fact it encodes (one per line)
RECALL: recite from the first beat of each line only, then expand
```

## Sub-mode: acrostic verse (藏头诗)

The payload hides in the **line-initial characters**: written vertically, the
first character of each line spells the key term or ordered list. The verse
is the carrier (meter + narrative hold the lines in order); the initials are
the retrieval cue — one per item. This is the classical Chinese first-letter
mnemonic, ~a millennium older than ROYGBIV-style acrostics.

- One item per line initial; never force a wrong initial for smoother verse.
- Prefer lines whose content also relates to the item (double coding).
- MAPPING reads down the initials; drill verse → list and list → verse.

Worked example (OSI layers, bottom-up):

```
People do need to see packets arrive.   → P D N T S P A
Physical, Data-link, Network, Transport, Session, Presentation, Application

MAPPING: each word's initial -> one OSI layer, in stack order
RECALL: recite the sentence, then expand each initial into its layer
```

## Sub-mode: shape rhyme (八卦-style)

The verse's content **verbally redraws a visual figure** — each line depicts
one element's shape as concrete objects, in reading order. Reciting the verse
reconstructs the picture: the phonological loop replays the description while
the mind's eye redraws it (dual coding in one artifact). Canonical form: the
trigram rhymes 乾三连、坤六断、震仰盂、艮覆碗 ("Qián: three unbroken; Kūn: six
broken; Zhèn: an upturned bowl; Gèn: an overturned bowl").

- Use only for figures simple enough to verbalize losslessly — else a diagram.
- Each line names shape features as objects (bowls, breaks, stacks), never
  abstractions.
- Drill both directions: verse → sketch and sketch → verse. Note that the
  verse carries the SHAPE, not the meaning — attach the concept separately.

Worked example (HTTP status-code families as shape):

```
One is a single pillar, still standing — 1xx: hold on, more coming.
Two is a pair of pillars, gate complete — 2xx: success, you're through.
Four is a broken gate, fallen inward — 4xx: your request broke it.
Five is a gate collapsed on the keeper — 5xx: the server broke itself.

MAPPING: each line's drawn figure -> one status family and its meaning
RECALL: recite a line, sketch its figure, then name the family
```

## Checklist — before emitting a verse

```
[ ] Content is a genuinely ORDERED, verbatim sequence (else prose/palace/diagram)
[ ] ≤ ~30 items; one fixed meter; line-ends rhyme
[ ] Triplets used for list-like content
[ ] Every line has ONE concrete, pictureable image — zero abstract filler nouns
[ ] No fact distorted to fit the meter
[ ] It chants when read aloud
[ ] MAPPING given (line -> fact); ends with a RECALL instruction
```
