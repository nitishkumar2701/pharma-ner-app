# Specimen — Drug & Disease Lookup

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
  symptoms / prevention / when to see a doctor. The provider is switchable
  — see below.
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

## Run it locally

```bash
cd pharma-ner-app
python3 -m venv venv && source venv/bin/activate      # optional but recommended
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your real ANTHROPIC_API_KEY
export $(grep -v '^#' .env | xargs)   # or use python-dotenv / your shell's env loading

python app.py
# open http://localhost:5000
```

Get an API key at https://console.anthropic.com/settings/keys (Anthropic
API access is billed separately from any Claude.ai subscription).

### Using a free LLM provider instead

`llm_service.py` supports four providers, switched with the `LLM_PROVIDER`
variable in `.env` — no other code needs to change:

| `LLM_PROVIDER` | Cost | Get a key |
|---|---|---|
| `anthropic` (default) | Paid | https://console.anthropic.com/settings/keys |
| `groq` | Free tier, generous limits, fast | https://console.groq.com/keys |
| `gemini` | Free tier | https://aistudio.google.com/apikey |
| `ollama` | Fully free, runs locally, no key | https://ollama.com |

Example `.env` for the free Groq option:

```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your-real-key-here
GROQ_MODEL=llama-3.3-70b-versatile
```

For fully offline/local use with Ollama (no API key, no internet needed
once the model is downloaded):

```bash
# install Ollama from https://ollama.com, then:
ollama pull llama3.1
ollama serve   # usually starts automatically after install
```

```
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1
```

Open-weight models (Llama via Groq/Ollama) are generally a bit less
consistent at strict JSON formatting than Claude — `llm_service.py` already
strips common wrapping like ` ```json ` fences, but if you see occasional
"could not be parsed" results, that's why. Gemini and Claude tend to be the
most reliable for clean structured output.

### Add the full CDR dataset (optional, recommended)

The sample file only has a handful of terms. For much broader coverage,
download the official BC5CDR corpus:

- `CDR_TrainingSet.PubTator.txt`
- `CDR_DevelopmentSet.PubTator.txt`
- (optionally `CDR_TestSet.PubTator.txt`)

from https://biocreative.bioinformatics.udel.edu/tasks/biocreative-v/track-3-cdr/
(or the NCBI mirror), and drop them into `data/`. The app rebuilds
`entity_dict.json` automatically the next time it starts, since it checks
file modification times against the cached dictionary. Even without them,
unmatched terms are still classified by Claude directly — the dictionary
only adds a confidence hint and MeSH ID, it isn't required for the app to work.

## Deploy to Render (live URL)

**Option A — Blueprint (fastest)**

1. Push this folder to a GitHub repository.
2. In the Render dashboard: **New → Blueprint**, connect the repo. Render
   reads `render.yaml` and creates the web service automatically.
3. When prompted, set the `ANTHROPIC_API_KEY` environment variable to your
   real key (it's marked `sync: false` in the blueprint so Render asks for
   it rather than committing it).
4. Click **Apply**. Render installs `requirements.txt` and runs
   `gunicorn app:app`. First deploy takes a couple of minutes.
5. Your app is live at `https://<service-name>.onrender.com`.

**Option B — Manual web service**

1. Push the folder to GitHub (or GitLab/Bitbucket).
2. In Render: **New → Web Service**, connect the repo.
3. Settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Under **Environment → Environment Variables**, add:
   - `ANTHROPIC_API_KEY` = your key from console.anthropic.com
   - `ANTHROPIC_MODEL` = `claude-sonnet-5` (or another available model string)
5. Click **Create Web Service**. Render builds and deploys; you get a live
   `onrender.com` URL once it's done.

**Notes**

- Render's free tier spins the service down after inactivity — the first
  request after idling will be slow (cold start), which is normal.
- Never commit your API key. `.env` is for local use only; on Render it's
  set through the dashboard's environment variables, which are encrypted
  at rest and not exposed in your repo.
- If you add the full CDR dataset, the first boot after deploy will take a
  little longer while it builds `entity_dict.json` — after that it's
  cached and loads instantly on restarts (until the source files change).

## API reference

- `POST /api/search` — body `{"term": "clonidine"}` → classification +
  AI-written note.
- `POST /api/analyze` — body `{"text": "..."}` → entities found + HTML with
  `<mark>` tags for highlighting.
- `GET /api/health` — status, indexed term count, whether the API key is set.
