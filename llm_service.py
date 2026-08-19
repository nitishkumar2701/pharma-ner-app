import os
import json
import time

import requests

SYSTEM_PROMPT = """You are a biomedical assistant inside a drug/disease lookup app.

Given a search term, do two things:
1. Classify it as exactly one of: "drug" (a medication, chemical, or substance),
   "disease" (an illness, condition, or disorder), or "unknown" (neither, or
   you are not confident).
2. Write a short, plain-language note about it.
3. Try to summarise and if the content is longer than two sentences and make it easily understandable.

Respond with ONLY a single valid JSON object, no markdown fences and no text
before or after it, matching one of these schemas exactly:

If type is "drug":
{"type": "drug", "name": "<canonical name>", "used_for": "<1-2 sentences on what conditions it treats>", "how_it_works": "<one short sentence>", "common_side_effects": "<short comma-separated list>", "disclaimer": "This is general information, not medical advice."}

If type is "disease":
{"type": "disease", "name": "<canonical name>", "overview": "<1-2 sentence description>", "symptoms": "<short comma-separated list>", "prevention": "<1-2 sentences on prevention or management>", "when_to_see_doctor": "<one short sentence>", "disclaimer": "This is general information, not medical advice."}

If type is "unknown":
{"type": "unknown", "name": "<the term as given>", "note": "<one sentence explaining you could not confidently classify this>"}

Be concise and factual. Never speculate or invent facts you are not confident about."""


import re


def _clean_json(text):
    text = text.strip().strip("`").strip()
    if text.lower().startswith("json"):
        text = text[4:].strip()

    # Some models add a sentence before/after the JSON object even when
    # told not to. Pull out the first {...} block as a fallback.
    if not (text.startswith("{") and text.endswith("}")):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)

    return text


def _build_user_prompt(term, hint_label):
    hint = ""
    if hint_label == "Chemical":
        hint = " (An internal biomedical reference dataset tags this as a chemical/drug.)"
    elif hint_label == "Disease":
        hint = " (An internal biomedical reference dataset tags this as a disease.)"
    return f'Term: "{term}"{hint}'


class LLMService:
    """
    Talks to whichever LLM provider is configured via LLM_PROVIDER:

      - "gemini"               -> Google Gemini free tier.
                                  https://aistudio.google.com

    Set LLM_PROVIDER plus the matching API key env var in .env. Everything
    downstream (app.py, the frontend) is unaffected by which provider is used.
    """

    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

    def is_configured(self):
        if self.provider == "gemini":
            return bool(self.gemini_key)
        return False

    def describe(self, term, hint_label=None):
        prompt = _build_user_prompt(term, hint_label)

        if self.provider == "gemini":
            raw = self._call_gemini(prompt)
        else:
            raise RuntimeError(f"Unknown LLM_PROVIDER '{self.provider}'.")

        try:
            return json.loads(_clean_json(raw))
        except json.JSONDecodeError:
            print("---- LLM raw response that failed to parse ----")
            print(raw)
            print("------------------------------------------------")
            return {
                "type": "unknown",
                "name": term,
                "note": "The AI response could not be parsed. Please try again.",
            }

    # ---------- providers ----------

    def _call_gemini(self, prompt):
        if not self.gemini_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey and add it to .env."
            )
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.gemini_model}:generateContent?key={self.gemini_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 5000},
        }

        last_error = None
        for attempt in range(3):
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 503:
                # Google's free tier gets deprioritized under load; a short
                # backoff and retry clears this most of the time.
                last_error = requests.exceptions.HTTPError(
                    "503 Service Unavailable (model overloaded)", response=resp
                )
                time.sleep(1.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("candidates") or []
            if not candidates:
                feedback = data.get("promptFeedback", {})
                reason = feedback.get("blockReason", "no candidates returned")
                raise RuntimeError(f"Gemini returned no result ({reason}).")

            parts = candidates[0].get("content", {}).get("parts") or []
            if not parts or "text" not in parts[0]:
                finish_reason = candidates[0].get("finishReason", "unknown")
                raise RuntimeError(f"Gemini returned an empty response (finishReason: {finish_reason}).")

            return parts[0]["text"]

        raise RuntimeError(
            "Gemini's servers are overloaded right now (503, even after retries). "
            "This is common on the free tier during peak times — please try again "
            "in a moment."
        ) from last_error
