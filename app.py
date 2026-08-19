import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify

from entity_extractor import EntityExtractor
from llm_service import LLMService

# Load variables from a local .env file (if present) into the process
# environment. On Render (and most hosts) env vars are already injected
# directly, so this is a no-op there — it only matters for local runs.
load_dotenv()

app = Flask(__name__)

DATA_DIR = "data"
ENTITY_DICT_PATH = os.path.join(DATA_DIR, "entity_dict.json")

# Any PubTator-formatted file dropped into data/ with one of these names
# (or matching CDR_*.PubTator.txt) is picked up automatically at startup.
SOURCE_FILES = [
    os.path.join(DATA_DIR, "CDR_TrainingSet.PubTator.txt"),
    os.path.join(DATA_DIR, "CDR_DevelopmentSet.PubTator.txt"),
    os.path.join(DATA_DIR, "CDR_TestSet.PubTator.txt"),
    os.path.join(DATA_DIR, "CDR_sample.PubTator.txt"),
]

extractor = EntityExtractor(SOURCE_FILES, ENTITY_DICT_PATH)
extractor.load_or_build()

llm = LLMService()


@app.route("/")
def index():
    return render_template("index.html", term_count=extractor.term_count())


@app.route("/api/search", methods=["POST"])
def search():
    payload = request.get_json(silent=True) or {}
    term = (payload.get("term") or "").strip()

    if not term:
        return jsonify({"error": "Please enter a drug or disease name."}), 400
    if len(term) > 120:
        return jsonify({"error": "That search term is too long."}), 400

    match = extractor.lookup(term)
    hint_label = match["label"] if match else None

    try:
        result = llm.describe(term, hint_label=hint_label)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"AI lookup failed: {exc}"}), 502

    return jsonify({
        "query": term,
        "dictionary_match": match,
        "result": result,
    })


@app.route("/api/analyze", methods=["POST"])
def analyze():
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()

    if not text:
        return jsonify({"entities": [], "html_text": ""})
    if len(text) > 20000:
        return jsonify({"error": "Text is too long (max 20,000 characters)."}), 400

    entities = extractor.scan_text(text)
    html_text = extractor.highlight(text, entities)
    return jsonify({"entities": entities, "html_text": html_text})


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "dictionary_terms": extractor.term_count(),
        "llm_configured": llm.is_configured(),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
