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

      - "anthropic" (default) -> Claude, via the Anthropic API. Paid.
      - "groq"                -> Llama models via Groq's free tier.
                                  https://console.groq.com
      - "gemini"               -> Google Gemini free tier.
                                  https://aistudio.google.com
      - "ollama"                -> A fully local, fully free model via Ollama.
                                  https://ollama.com (no API key needed)

    Set LLM_PROVIDER plus the matching API key env var in .env. Everything
    downstream (app.py, the frontend) is unaffected by which provider is used.
    """

    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "gemini").lower()

        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        self.anthropic_model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

        self.groq_key = os.environ.get("GROQ_API_KEY")
        self.groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

        self.ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.1")

    def is_configured(self):
        if self.provider == "anthropic":
            return bool(self.anthropic_key)
        if self.provider == "groq":
            return bool(self.groq_key)
        if self.provider == "gemini":
            return bool(self.gemini_key)
        if self.provider == "ollama":
            return True  # no key needed, assumed reachable locally
        return False

    def describe(self, term, hint_label=None):
        prompt = _build_user_prompt(term, hint_label)

        if self.provider == "anthropic":
            raw = self._call_anthropic(prompt)
        elif self.provider == "groq":
            raw = self._call_groq(prompt)
        elif self.provider == "gemini":
            raw = self._call_gemini(prompt)
        elif self.provider == "ollama":
            raw = self._call_ollama(prompt)
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

    # def _call_anthropic(self, prompt):
    #     if not self.anthropic_key:
    #         raise RuntimeError(
    #             "ANTHROPIC_API_KEY is not set. Add it to .env, or switch "
    #             "LLM_PROVIDER to 'groq', 'gemini', or 'ollama' for a free option."
    #         )
    #     from anthropic import Anthropic

    #     client = Anthropic(api_key=self.anthropic_key)
    #     message = client.messages.create(
    #         model=self.anthropic_model,
    #         max_tokens=500,
    #         system=SYSTEM_PROMPT,
    #         messages=[{"role": "user", "content": prompt}],
    #     )
    #     return "".join(b.text for b in message.content if b.type == "text")

    def _call_groq(self, prompt):
        if not self.groq_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Get a free key at "
                "https://console.groq.com/keys and add it to .env."
            )
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.groq_key}"},
            json={
                "model": self.groq_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 500,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_gemini(self, prompt):
        if not self.gemini_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey and add it to .env."
            )
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.gemini_model}:generateContent?key="
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

    def _call_ollama(self, prompt):
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                "Could not reach Ollama at "
                f"{self.ollama_url}. Install it from https://ollama.com, run "
                f"'ollama pull {self.ollama_model}', and make sure it's running."
            ) from exc
        return resp.json()["message"]["content"]
