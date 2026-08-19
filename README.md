# RX Specimen

A rebuild of the original spaCy/PubTator NER Flask app into a modern lookup
tool: search any drug or disease name, get an instant Chemical/Disease
classification plus an AI-written note (what it treats / symptoms &
prevention). A "passage scan" mode also highlights known terms in pasted
text, carrying over the original `/predict` highlighting feature.

## How it works

- **Reference index** — `entity_extractor.py` parses any PubTator-formatted
  file in `data/` (same format as the BC5CDR `CDR_TrainingSet` /
  `CDR_DevelopmentSet` files the original project used) and builds a
  `term → {label, mesh_id}` dictionary. This replaces the spaCy training
  step: search terms are usually single words or short phrases, and a
  frequency-based lookup built directly from the annotated spans is faster,
  needs no training time, and is exactly as accurate as the dataset. A
  small sample file ships in `data/CDR_sample.PubTator.txt` so the app has
  a few terms indexed out of the box.
- **AI note** — `llm_service.py` calls an LLM with the search term (and a
  hint from the reference index, if matched) and asks for a small JSON
  object: what a drug treats / how it works / side effects, or a disease's
  symptoms / prevention / when to see a doctor.
- **Frontend** — `templates/index.html` + `static/` is a single page, no
  build step, calling `/api/search` and `/api/analyze`.

## Project structure

```
pharma-ner-app/
├── app.py                 # Flask routes
├── entity_extractor.py    # PubTator parsing + lookup dictionary
├── llm_service.py         # Anthropic API wrapper
├── requirements.txt
├── Procfile                # gunicorn start command
├── render.yaml             # Render blueprint (optional one-click deploy)
├── .env.example
├── data/
│   └── CDR_sample.PubTator.txt
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    └── js/app.js
```

| `LLM_PROVIDER` | Cost | Get a key |
|---|---|---|
| `gemini` | Free tier | https://aistudio.google.com/apikey |


