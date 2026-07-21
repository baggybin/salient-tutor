# Phase 0: The Mnemonic Generation Bible

*Insert this as the cognitive foundation layer that feeds into your existing Phase 1 prompt.*

Below is a complete expansion that formalizes the Von Restorff, Bizarreness, and Emotional Arousal effects into a hard rule-set your LLM can follow. I have kept the framework faithful to actual cognitive science — there is a real neuroscience reason this works, and the engineering follows from it.

---

## 0.1 — Why Bizarre Imagery Actually Works (The Neuroscience)

Three distinct, peer-reviewed phenomena converge here. They are often confused, but they are three separate cognitive mechanisms that stack:

### A. The Von Restorff Effect (Isolation Effect)
- **Discovered:** Hedwig von Restorff (1933)
- **Mechanism:** When a homogeneous series contains one distinctive item, that item is recalled at 2–3× the rate of the others.
- **Application to your pipeline:** Your SVG is a "homogeneous series" of typical icons (servers, packets, gears). To break the series, every locus must be *visually impossible to confuse* with anything else in the palace.
- **Rule:** No two loci may share a dominant shape, color family, or silhouette.

### B. The Bizarreness Effect
- **Discovered:** McDaniel & Einstein (1986); elaborated by Waddill & McDaniel (1978)
- **Mechanism:** Bizarre imagery produces deeper *elaborative encoding* than common imagery. The brain treats impossible objects as "puzzles" and assigns them more semantic weight during consolidation.
- **Quantified effect size:** Bizarre sentences/images are recalled ~25–40% better than common ones in paired-associate tasks.
- **Critical nuance:** This works best for **concrete nouns** (your `technicalFact` keywords). Abstract concepts must first be made concrete — see 0.3 below.

### C. Emotional Arousal & Amygdala-Mediated Consolidation
- **Mechanism:** The amygdala modulates hippocampal consolidation. Emotionally arousing events — positive or negative — are preferentially transferred to long-term memory (Cahill & McGaugh, 1998).
- **Sub-categories that boost encoding:**
  1. **Humor** (the dopamine reward of "getting the joke")
  2. **Disgust/mild revulsion** (strong negative valence, high salience)
  3. **Mild embarrassment or taboo violation** (social-risk encoding)
  4. **Sexual salience** (high attentional capture via evolutionary relevance)
  5. **Violence/danger** (threat-detection systems activate)

The user prompt's intuition is correct on the science: sexual and odd images *do* help memory, precisely because the attentional system flags them as high-priority and the amygdala tags them for consolidation. **However** — and this is important engineering guidance for your system prompts — **sexual content has a sharp utility ceiling in technical education** because:

1. It is contextually incongruent with the topic and breaks immersion in the "palace"
2. It generates content moderation failures
3. Its distinctiveness fades fast (it stops being novel after the 3rd use)
4. It rarely maps semantically to technical concepts (TCP handshake ≠ erotic content)

The **highest-yield arousal categories for technical loci are humor, absurdity, scale violation, and gentle disgust.** Bake these in as the primary tools. Reserve the others sparingly.

---

## 0.2 — The Six Memory-Multiplier Properties

Every locus must score on at least **four** of these six axes. I recommend hard-coding this as a self-check in the Phase 1 system prompt:

| Property | What it means | Example (bad → good) |
|---|---|---|
| **Novelty** | Never seen before in any diagram | Server → server with human teeth |
| **Violation** | Breaks a physical or social rule | Sitting → server sitting in a dentist's chair |
| **Motion implication** | Static image suggests action | Static → server mid-leap off a cliff |
| **Scale violation** | Wrong-sized elements | Normal → mouse the size of the server |
| **Sensory specificity** | Engages multiple senses | "Big" → "slimy, neon-green, humming" |
| **Self-reference hook** | Triggers a personal association | Generic → your childhood dentist's office |

**Embedding rule for Phase 1 prompt:**
```text
Before finalizing any locus, verify it scores ≥ 4/6 on the Memory-Multiplier Properties table. If not, regenerate with at least one more violating axis.
```

---

## 0.3 — The Abstraction Bridge (Critical for Technical Concepts)

TCP, recursion, garbage collection, mutexes — these are abstract. Abstract concepts cannot be encoded bizarrely *directly*; the cognitive science is clear on this (the bizarreness effect requires concrete referents). You must build a **two-stage bridge**:

```
ABSTRACT CONCEPT
    ↓
Concrete Metaphor (the LLM must pick this first)
    ↓
Bizarre Visualization of the Metaphor (Phase 1 visualDescription)
```

### Concrete Metaphor Mapping Table (seed for your prompt)

| Abstract concept | Good metaphor base | Bizarre visualization |
|---|---|---|
| TCP handshake (SYN/SYN-ACK/ACK) | Two people meeting | A formal handshake where both people have lobster claws |
| Mutex / lock | A single bathroom key | The bathroom key is on a live, hissing cobra |
| Recursion | A mirror facing a mirror | A mirror reflecting itself, but each reflection is wearing different period costumes |
| Garbage collection | A street sweeper | The sweeper is a sentient vacuum cleaner with a top hat, eating broken code |
| DNS resolution | A phone book | The phone book is alive, has opinions, and refuses to give you numbers it doesn't like |
| SQL injection | A bouncer at a door | The bouncer has no face and lets anyone in if they whisper "OR 1=1" |

**System prompt add-on for Phase 1:**
```text
Step 0: For each locus, first state the CONCRETE METAPHOR (one sentence) that maps the abstract concept.
Step 1: Then generate a visualDescription that violates 4+ of the Memory-Multiplier Properties on that metaphor.
Output the metaphor as "metaphorAnchor" inside the locus object.
```

Updated schema:
```json
{
  "locusId": "tcp-syn-courier",
  "metaphorAnchor": "Two strangers performing a formal handshake",
  "visualDescription": "Two figures in Victorian tailcoats extending arms; each hand is replaced by a giant, dripping-wet lobster claw that snaps shut with audible menace; one claw holds a SYN flag, the other a SYN-ACK flag, in 17th-century wax-seal style",
  "technicalFact": "TCP handshake begins with SYN, followed by SYN-ACK, then ACK"
}
```

The `metaphorAnchor` becomes a debug field for your frontend — you can show it as a "hint" after the user fails recall twice.

---

## 0.4 — The Anti-Mundanity Hard Filter

The biggest failure mode of memory palace LLMs is that they default to literal icons. You must add a **negative constraint list** to your Phase 1 system prompt. Tokens that are BANNED unless explicitly mutated:

```text
BANNED VISUAL TOKENS (unless mutated/bizarre):
- Generic boxes, cylinders, or 3D shapes
- Anything resembling a stock icon (gear, cloud, server rack) UNLESS mutated
- Human figures in normal poses
- Animals acting naturally
- Color palettes limited to standard UI colors (#3B82F6, etc.)
- Anything that could appear in an AWS architecture diagram
```

**Replacement rule:** Every "banned" element must be replaced by its *opposite* on at least one axis (scale, material, behavior, era, or agency).

---

## 0.5 — The Serial Position Killer

Memory palaces built in sequence (Room 1 → Room 2 → ... → Room N) suffer from the **primacy and recency effects** — the first and last rooms are remembered, the middle rooms vanish. This is the *biggest unsolved problem* in the memory palace literature, and your pipeline must address it.

### Three architectural solutions:

1. **Spatial non-linearity:** Place the most important/conceptually dense loci at the geographic extremes of the SVG (top-left, bottom-right corners). The eye notices corners first.

2. **Emotional ramping:** Make the middle rooms the *most* bizarre, not the least. Crank the absurdity dial to 11 in the middle of the palace, then taper it. The brain encodes emotional peaks best.

3. **Cross-room callbacks:** Have objects from Room 1 reappear mutated in Room 5. This creates a *recognition network* — when the user remembers Room 1, the callback triggers recall of Room 5.

**Add to your Phase 1 prompt:**
```text
ARCHITECTURE RULE: Do not distribute loci with uniform absurdity.
- First and last loci of each room: 4/6 Memory-Multiplier score
- Middle loci of each room: 6/6 Memory-Multiplier score
- Cross-reference at least one object from a prior room in a mutated form (specify as "callbackTo": "locusId-of-previous")
```

---

## 0.6 — The Active Recall CSS Layer (Frontend Enhancement)

You already have the grayscale/blur reveal mechanism in Phase 2. Add one more layer for spaced repetition:

```javascript
// Pseudocode for the recall state machine
const recallStates = {
  HIDDEN:      { filter: 'grayscale(100%) blur(5px)', opacity: 0.5 },
  HINTED:      { filter: 'grayscale(50%) blur(2px)',  opacity: 0.7 }, // metaphorAnchor visible
  ATTEMPTED:   { filter: 'grayscale(20%) blur(0.5px)',opacity: 0.85 }, // color tint
  REVEALED:    { filter: 'none',                      opacity: 1.0 }
};
```

Track transitions in `localStorage`. After 3 successful recall cycles, promote the locus to `MASTERED` (no blur, just locked in gold border). This converts your pipeline from a "see the picture, read the fact" toy into a true **spaced repetition system**.

---

## 0.7 — Full Revised Phase 1 System Prompt

Combining everything above into the final, hardened prompt:

```text
You are an expert cognitive psychologist specializing in the Method of Loci. Break down the requested technical concept into a spatial memory palace grounded in three peer-reviewed mechanisms: the Von Restorff isolation effect, the Bizarreness Effect (McDaniel & Einstein, 1986), and amygdala-mediated emotional consolidation.

=== MNEMONIC GENERATION LAWS ===

1. ZERO MUNDANITY: Banned visual tokens (boxes, gears, clouds, normal humans, normal animals, AWS-diagram shapes) UNLESS explicitly mutated. Apply scale, material, behavior, era, or agency violation to every element.

2. SIX-AXIS SCORING: Every locus must score ≥ 4/6 on:
   - Novelty | Violation | Motion implication | Scale violation | Sensory specificity | Self-reference hook

3. ABSTRACTION BRIDGE: For each abstract concept, first state a concrete metaphor (output as "metaphorAnchor"), then visualize that metaphor bizarrely.

4. EMOTIONAL RAMPING: Middle loci in a room must score 6/6 (highest absurdity). Endpoints score 4/6.

5. CROSS-ROOM CALLBACKS: At least one object per room must mutate-reference a prior locus (output as "callbackTo").

6. AROUSAL HIERARCHY (in order of utility for technical content):
   Primary:   Humor, Absurdity, Scale violation, Disgust (mild)
   Secondary: Social taboo (gentle), Danger/imperilment
   Tertiary:  Sexual salience (use sparingly; contextually map to concept)

=== OUTPUT SCHEMA ===

{
  "palaceTheme": "Vivid environment description",
  "cognitiveProfile": "Which memory effects dominate this palace (e.g., 'high bizarreness, low sexual salience, strong humor')",
  "rooms": [
    {
      "roomId": "kebab-case-room-id",
      "roomName": "Plain text",
      "conceptTaught": "Technical concept",
      "boundingBox": { "x": 0, "y": 0, "w": 1920, "h": 540 },
      "loci": [
        {
          "locusId": "kebab-case-g-tag-id",
          "metaphorAnchor": "One-sentence concrete metaphor",
          "visualDescription": "Detailed bizarre prompt for SVG generator; must satisfy 4+/6 axes",
          "callbackTo": "optional-locusId-from-prior-room",
          "arousalChannel": "humor | disgust | taboo | danger | sexual | absurdity",
          "technicalFact": "Literal fact being encoded",
          "boundingBox": { "x": 0, "y": 0, "w": 300, "h": 300 }
        }
      ]
    }
  ]
}

No markdown wrappers. Raw JSON only.
```

---

## 0.8 — The No-Repeat Imagery Law (千字文 Constraint)

The 千字文 (Thousand Character Classic, ~6th c.) was composed from exactly 1,000 non-repeating characters — uniqueness enforced as a compositional law, fourteen centuries before the lab named the mechanism. Adopt it as a hard rule for every palace, verse, or peg set your pipeline emits:

```text
NO-REPEAT LAW: Within one image set, every anchor image must be unique.
Before placing a new image, diff it against every image already placed on
three axes: dominant shape, color family, and action/creature. A collision on
any axis = mutate the new image (scale, material, species, era) and re-check.
Deliberate callbacks (§0.5) are the only reuse allowed — and they must MUTATE
the quoted image, never clone it.
```

**Why it is a law and not a preference:** the Von Restorff effect (§0.1A) collapses the moment oddities repeat — two giants, two fires, two melting objects merge into one smeared trace. Worse, duplicate anchors create **cue overload** (the fan effect, Anderson 1974): one cue now points at two targets and retrieval slows and degrades for both. Uniqueness is what keeps every locus a clean one-to-one cue→fact mapping.

---

## Appendix — Classical Chinese Techniques, Mapped to the Lab

Five classical Chinese mnemonic practices predate the modern literature by one to two millennia. None is folk superstition — each is an independent discovery of a mechanism the lab later quantified. Use them as prior art and as authoring patterns.

| Classical technique | What it is | Modern lab finding it implements |
|---|---|---|
| **九九歌** (nine-nines chant, ~2,200 yrs) | The multiplication table recited as a fixed-cadence rhymed chant until it becomes a motor routine | **Chunking + phonological cueing**: rhythm and rhyme are external retrieval constraints — partial recall completes itself (Rubin 1995 on oral traditions) |
| **三字经** (Three-Character Classic, ~13th c.) | A whole curriculum written in 3-character lines | **Chunking at optimal group size**: 3–4-item rhythmic groups maximize serial recall (Miller 1956; Mathy & Feldman 2012) — the beat makes a malformed chunk instantly audible |
| **千字文** (Thousand Character Classic, ~6th c.) | A primer composed of exactly 1,000 non-repeating characters | **Distinctiveness / anti-cue-overload**: unique items avoid the fan effect and preserve the isolation effect (von Restorff 1933; Anderson 1974) — see §0.8 |
| **谐音** (number homophones, living practice) | Numbers recoded into soundalike phrases — 520 → "I love you", 168 → "road to prosperity" | **Phonological recoding / free peg system**: meaningless digit strings become meaningful, imageable chunks (transfer-appropriate processing; the culture-specific cousin of the Major System) |
| **掐指一算** ("pinching the fingers to reckon") | The 12 finger joints used as an ordered locus map for calendrical cycles | **Method of loci on a body-based scaffold**: an over-learned, always-available spatial order plus a motor/proprioceptive trace — a portable palace for ≤12 items |
| **永字八法** (Eight Principles of Yong) | All eight calligraphy brush strokes taught through the one character 永 that contains them all | **Worked-example / schema abstraction**: one canonical exemplar carries a whole category; variants are learned as deltas against it (Sweller 1998; Gick & Holyoak 1983) |
| **歇后语** (xiēhòuyǔ, two-part allegorical sayings) | A vivid concrete mini-scene, then the punchline meaning: "a mud bodhisattva crosses the river — it can't even save itself" | **Concreteness + imagery-with-meaning**: the scene enacts the fact, so the image cues the meaning directly (Paivio 1971; Bower 1972) — the folk version of the `metaphorAnchor` (§0.3): concrete scene first, meaning revealed after |
| **藏头诗** (acrostic verse) | A poem whose line-initial characters spell the hidden key term or ordered list | **Organizational cueing / first-letter mnemonics**: narrative order + an orthographic cue per item (Bower 1970; Bellezza 1981) — predates Western acrostics (ROYGBIV) by ~a millennium |
| **八卦 trigram rhymes** (乾三连、坤六断…) | Verses that verbally describe the visual shape of each trigram | **Dual coding across working-memory codes**: the phonological loop replays a description that reconstructs the visuospatial figure (Paivio 1971; Baddeley 1986) |
| **对仗 / 笠翁对韵** (antithetical parallelism drills) | Strictly parallel antithetical pairs drilled call-and-response: 天对地，雨对风 ("sky/earth, rain/wind") | **Relational structure as retrieval cue / encoding specificity**: the parallel slot reinstates the partner, antithesis supplies the direction (Bower 1970; Tulving & Thomson 1973) |

**Testing effect note:** all of these were historically learned by recitation *to criterion* — chanting from memory, checking, repeating — which is successive relearning (retrieval practice + spacing), the strongest finding in the modern literature. The classical techniques supplied the encoding; the drill culture supplied the retrieval.

The pattern to internalize: **rhythm encodes order (九九歌, 三字经), uniqueness protects cues (千字文), sound recodes the arbitrary (谐音), and the body supplies a free palace (掐指一算).** When you author any mnemonic, you are choosing which of these four levers does the work.
