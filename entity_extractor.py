"""
Builds a Chemical/Disease lookup dictionary straight from PubTator-formatted
files (the same format as the BC5CDR CDR_TrainingSet / CDR_DevelopmentSet
files this project originally trained a spaCy NER model on).

Why a dictionary instead of a trained spaCy model?
- Search terms are usually a single word or short phrase ("aspirin",
  "type 2 diabetes"), not a full sentence -- spaCy's NER is trained and
  tuned on sentence-level context, so it under-performs on bare terms.
- A frequency-based lookup built directly from the annotated spans is fast,
  has zero training time (important for Render's free tier build/start
  limits), and is exactly as accurate as the underlying dataset's labels.
- It's still used for the free-text "scan a passage" feature below, which
  is a direct analogue of the original /predict endpoint.

Drop the full CDR_TrainingSet.PubTator.txt / CDR_DevelopmentSet.PubTator.txt
files (from https://biocreative.bioinformatics.udel.edu/tasks/biocreative-v/track-3-cdr/)
into data/ for full coverage. A small sample file ships with the repo so the
app works out of the box.
"""

import os
import re
import json
import difflib
from collections import defaultdict, Counter


class EntityExtractor:
    def __init__(self, source_files, dict_path):
        self.source_files = source_files
        self.dict_path = dict_path
        self.terms = {}  # lowercase term -> {"label": str, "count": int, "mesh_id": str}

    # ---------- building ----------

    def _parse_file(self, path, term_labels, term_mesh):
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.rstrip("\n")
                if not line or "|t|" in line or "|a|" in line:
                    continue

                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                if parts[0].strip().upper() == "" or parts[1].strip().upper() == "CID":
                    continue

                try:
                    int(parts[1])
                    int(parts[2])
                except ValueError:
                    continue

                text = parts[3].strip()
                label = parts[4].strip()
                mesh_id = parts[5].strip() if len(parts) > 5 else ""

                if not text or label not in ("Chemical", "Disease"):
                    continue

                key = text.lower()
                term_labels[key][label] += 1
                if mesh_id and mesh_id != "-1":
                    term_mesh[key] = mesh_id

    def build(self):
        term_labels = defaultdict(Counter)
        term_mesh = {}

        for path in self.source_files:
            self._parse_file(path, term_labels, term_mesh)

        self.terms = {}
        for term, counter in term_labels.items():
            label = counter.most_common(1)[0][0]
            self.terms[term] = {
                "label": label,
                "count": sum(counter.values()),
                "mesh_id": term_mesh.get(term, ""),
            }

        os.makedirs(os.path.dirname(self.dict_path) or ".", exist_ok=True)
        with open(self.dict_path, "w", encoding="utf-8") as f:
            json.dump(self.terms, f)

        print(f"Built entity dictionary with {len(self.terms)} unique terms.")

    def load_or_build(self):
        needs_build = True

        if os.path.exists(self.dict_path):
            newest_source = 0
            for p in self.source_files:
                if os.path.exists(p):
                    newest_source = max(newest_source, os.path.getmtime(p))
            if os.path.getmtime(self.dict_path) >= newest_source:
                needs_build = False

        if needs_build:
            self.build()
        else:
            with open(self.dict_path, "r", encoding="utf-8") as f:
                self.terms = json.load(f)
            print(f"Loaded cached entity dictionary with {len(self.terms)} terms.")

    # ---------- querying ----------

    def term_count(self):
        return len(self.terms)

    def lookup(self, query):
        """Exact (case-insensitive) or fuzzy match for a single search term."""
        key = query.strip().lower()
        if not key:
            return None

        if key in self.terms:
            info = self.terms[key]
            return {
                "matched_term": key,
                "label": info["label"],
                "confidence": "exact",
                "mesh_id": info["mesh_id"],
            }

        close = difflib.get_close_matches(key, self.terms.keys(), n=1, cutoff=0.82)
        if close:
            info = self.terms[close[0]]
            return {
                "matched_term": close[0],
                "label": info["label"],
                "confidence": "fuzzy",
                "mesh_id": info["mesh_id"],
            }

        return None

    def scan_text(self, text):
        """Find all known Chemical/Disease terms in a longer passage."""
        lowered = text.lower()
        found = []

        for term, info in self.terms.items():
            if len(term) < 3:
                continue
            for m in re.finditer(re.escape(term), lowered):
                found.append({
                    "text": text[m.start():m.end()],
                    "label": info["label"],
                    "start": m.start(),
                    "end": m.end(),
                })

        found.sort(key=lambda e: (e["start"], -(e["end"] - e["start"])))

        filtered = []
        for e in found:
            if filtered and e["start"] < filtered[-1]["end"]:
                continue
            filtered.append(e)
        return filtered

    @staticmethod
    def highlight(text, entities):
        html = []
        last_end = 0
        for e in entities:
            html.append(text[last_end:e["start"]])
            css_class = e["label"].lower()
            html.append(f'<mark class="{css_class}">{text[e["start"]:e["end"]]}</mark>')
            last_end = e["end"]
        html.append(text[last_end:])
        return "".join(html)
