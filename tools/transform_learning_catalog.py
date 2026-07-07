#!/usr/bin/env python3
"""Transform learning_methods_catalog.json -> pedagogy_bundle.json nodes/edges +
a prose source file the ingest slices. Re-runnable: strips prior additions
(marked by source_file) before re-appending, so it never duplicates."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "learning_methods_catalog.json"
BUNDLE = ROOT / "data" / "pedagogy_bundle.json"
PROSE_REL = "extracted/learning-methods.txt"           # relative to data/ (source_root)
PROSE_ABS = ROOT / "data" / PROSE_REL

TIER_COMMUNITY = {
    "encoding":      (100, "Encoding & Mnemonic Techniques"),
    "retrieval":     (101, "Retrieval & Generative Practice"),
    "scheduling":    (102, "Scheduling (Spacing / Interleaving)"),
    "metacognitive": (103, "Metacognition & Desirable Difficulties"),
}

# Discredited legacy nodes to drop — flagged by the catalog's `myths` list.
# The left/right-brain "learner" application and the Buzan "whole-brain / full
# cortical" rationale are pseudoscience the tutor must not teach as strategy.
# Real split-brain science is preserved (entity_roger_sperry stays); only the
# learning-strategy framing is pruned. Speed-reading nodes are intentionally
# left in place (pacing has some support; out of scope for the myths list).
PRUNE_IDS = {
    "concept_brain_hemisphere_specialisation",
    "rationale_imagination_cortical_satisfaction",
}

def slug(cid): return cid.replace("-", "_")

def cite_str(c):
    return f"{c['authors']} ({c['year']}): {c['finding']}"

cat = json.loads(CATALOG.read_text())
techs = cat["batch_1_encoding"] + cat["batch_2_retrieval_scheduling_metacognitive"]

# ── 1. build the prose file, tracking 1-indexed inclusive line ranges ──
lines = []
tech_range = {}   # slug -> (a,b) for the technique block
rat_range = {}    # slug -> (a,b) for the rationale block

def emit_block(header, body_lines):
    """Append a block; return (start,end) 1-indexed inclusive. Flattens any
    embedded newlines so one list element == one physical line (else the
    source_location line ranges drift past multi-line how_to/failure fields)."""
    flat = [ln for item in body_lines for ln in str(item).split("\n")]
    start = len(lines) + 1
    lines.append(header)
    lines.extend(flat)
    lines.append("")           # blank separator
    end = len(lines) - 1       # last content line (before the blank)
    return start, end

for t in techs:
    s = slug(t["id"])
    ev = t["evidence"]
    aliases = ", ".join(t.get("aliases", []))
    # technique block -> concept node prose
    body = [
        f"Aliases: {aliases}." if aliases else "",
        t["definition"],
        "",
        "How to apply:",
        t["how_to"],
        "",
        "Use when: " + "; ".join(t.get("use_when", [])) + ".",
        "Avoid when: " + "; ".join(t.get("avoid_when", [])) + ".",
        "",
        "Common failure modes:",
        t["failure_modes"],
        "",
        f"Worked example ({t['worked_example']['domain']}): {t['worked_example']['text']}",
    ]
    tech_range[s] = emit_block(f"=== {t['name']} ===", [l for l in body])
    # rationale block -> rationale node prose
    rbody = [
        t["mechanism"],
        "",
        f"Evidence grade: {ev['grade']} (confidence {ev['confidence']}, "
        f"primarily {ev['source_class']}).",
        f"Caveats: {ev['caveats']}",
        "",
        "Key studies:",
    ] + [f"- {cite_str(c)}" for c in ev.get("citations", [])]
    rat_range[s] = emit_block(f"=== Why {t['name']} works ===", rbody)

PROSE_ABS.parent.mkdir(parents=True, exist_ok=True)
PROSE_ABS.write_text("\n".join(lines) + "\n", encoding="utf-8")

# ── 2. build nodes + edges ──
def node(nid, label, ft, comm, a, b):
    return {
        "label": label, "file_type": ft, "source_file": PROSE_REL,
        "source_location": f"lines {a}-{b}", "source_url": None,
        "captured_at": None, "author": None, "contributor": None,
        "id": nid, "community": comm, "norm_label": label.lower(),
    }

new_nodes, new_edges = [], []
for t in techs:
    s = slug(t["id"])
    comm = TIER_COMMUNITY[t["tier"]][0]
    cid, rid = f"concept_{s}", f"rationale_{s}"
    ta, tb = tech_range[s]; ra, rb = rat_range[s]
    new_nodes.append(node(cid, t["name"], "concept", comm, ta, tb))
    new_nodes.append(node(rid, f"Why {t['name']} works", "rationale", comm, ra, rb))
    # rationale_for edge
    new_edges.append({"relation": "rationale_for", "confidence": "EXTRACTED",
                      "confidence_score": 1.0, "source_file": PROSE_REL,
                      "source_location": f"lines {ra}-{rb}", "weight": 1.0,
                      "source": rid, "target": cid})
    # composes_with -> conceptually_related_to (targets are catalog ids)
    for c in t.get("composes_with", []):
        tgt = f"concept_{slug(c['target'])}"
        new_edges.append({"relation": "conceptually_related_to",
                          "confidence": "EXTRACTED", "confidence_score": 1.0,
                          "source_file": PROSE_REL,
                          "source_location": f"lines {ta}-{tb}", "weight": 1.0,
                          "source": cid, "target": tgt})

# ── 3. merge into bundle (strip prior additions first, by source_file marker) ──
bundle = json.loads(BUNDLE.read_text())
bundle["nodes"] = [n for n in bundle["nodes"] if n.get("source_file") != PROSE_REL]
bundle["edges"] = [e for e in bundle["edges"] if e.get("source_file") != PROSE_REL]

# Drop discredited legacy nodes + any edge touching them (myths-list cleanup).
bundle["nodes"] = [n for n in bundle["nodes"] if n.get("id") not in PRUNE_IDS]
bundle["edges"] = [
    e for e in bundle["edges"]
    if e.get("source") not in PRUNE_IDS and e.get("target") not in PRUNE_IDS
]

# loci rename (labels only; ids stay stable for edge/membership integrity).
# Applies everywhere a label copy lives: top-level nodes, community labels, and
# the community.node_ids embedded label copies. "Journey" as a common word
# (e.g. "31-Stage Journey per Month") is left alone — only the branded name.
_RENAMES = {
    "The Journey Method (System of Loci)": "The Memory Palace (Method of Loci)",
    "Journey Method (System of Loci)": "Memory Palace (Method of Loci)",
    "Journey Method (Loci & Classical Mnemonics)": "Memory Palace (Loci & Classical Mnemonics)",
}
def _relabel(obj):
    if isinstance(obj, dict):
        for k in ("label", "norm_label"):
            v = obj.get(k)
            if isinstance(v, str):
                for a, b in _RENAMES.items():
                    v = v.replace(a, b).replace(a.lower(), b.lower())
                obj[k] = v
        for v in obj.values():
            _relabel(v)
    elif isinstance(obj, list):
        for v in obj:
            _relabel(v)
_relabel(bundle)

bundle["nodes"].extend(new_nodes)
bundle["edges"].extend(new_edges)

# communities: add the 4 tier buckets if absent
have = {c.get("id") for c in bundle.get("communities", [])}
for tier, (cid, label) in TIER_COMMUNITY.items():
    if cid not in have:
        bundle.setdefault("communities", []).append({"id": cid, "label": label})

# refresh node_type_counts
counts = {}
for n in bundle["nodes"]:
    counts[n.get("file_type", "?")] = counts.get(n.get("file_type", "?"), 0) + 1
bundle["node_type_counts"] = counts
meta = bundle.setdefault("metadata", {})
meta["corpus"] = (meta.get("corpus", "") +
                  " + evidence-graded learning-methods catalog (research-authored, 27 techniques)").strip(" +")

BUNDLE.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"prose file: {PROSE_ABS} ({len(lines)} lines)")
print(f"added nodes: {len(new_nodes)} (27 concept + 27 rationale)")
print(f"added edges: {len(new_edges)}")
print(f"node_type_counts: {counts}")
