"""Answer generation with four interchangeable engines:

- "anthropic": Claude, streamed (best quality; needs an API key)
- "gemini":    Google Gemini, streamed (free-tier API key, no install)
- "ollama":    a local open model via Ollama (free, private, no key)
- "extractive": no LLM; quotes the best-matching sentences

LLM_PROVIDER=auto (default) picks the first one available, in that order.
All engines yield text deltas, so the view streams them identically.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterator

import anthropic
import httpx
from django.conf import settings

from documents.services.retrieval import Hit, tokenize

from .grounding import SYSTEM_PROMPT, build_user_turn

log = logging.getLogger(__name__)

# Sentence ends, plus bullet characters: resumes and slides are lists without full stops.
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\s*[•▪●◦]\s*")


class AnswerError(RuntimeError):
    """A failure the user should see (e.g. rate limit), with a safe message."""


_ollama_cache: tuple[float, str] = (0.0, "offline")


def ollama_status() -> str:
    """"ready", "no-model" (running, but the model isn't pulled) or "offline". Cached for 15 s."""
    global _ollama_cache
    checked_at, status = _ollama_cache
    if time.monotonic() - checked_at < 15:
        return status
    try:
        tags = httpx.get(f"{settings.OLLAMA_URL}/api/tags", timeout=1.5).json()
        wanted = settings.OLLAMA_MODEL if ":" in settings.OLLAMA_MODEL else f"{settings.OLLAMA_MODEL}:latest"
        names = {m.get("name") for m in tags.get("models", [])}
        status = "ready" if wanted in names or settings.OLLAMA_MODEL in names else "no-model"
    except (httpx.HTTPError, ValueError):
        status = "offline"
    _ollama_cache = (time.monotonic(), status)
    return status


def provider() -> str:
    choice = settings.LLM_PROVIDER.lower()
    if choice in {"anthropic", "gemini", "ollama", "extractive"}:
        return choice
    if settings.ANTHROPIC_API_KEY:
        return "anthropic"
    if settings.GEMINI_API_KEY:
        return "gemini"
    if ollama_status() == "ready":
        return "ollama"
    return "extractive"


def llm_enabled() -> bool:
    return provider() != "extractive"


def mode() -> str:
    """Label stored with each answer: the model that wrote it."""
    return {"anthropic": settings.ANTHROPIC_MODEL, "gemini": settings.GEMINI_MODEL,
            "ollama": f"ollama/{settings.OLLAMA_MODEL}"}.get(provider(), "extractive")


def stream_answer(question: str, hits: list[Hit], history: list[dict]) -> Iterator[str]:
    if not hits:
        yield "I couldn't find anything relevant in your documents for that question. Try rephrasing it, or check that the right documents are selected."
        return
    engine = provider()
    if engine == "anthropic":
        yield from _stream_claude(question, hits, history)
    elif engine == "gemini":
        yield from _stream_gemini(question, hits, history)
    elif engine == "ollama":
        yield from _stream_ollama(question, hits, history)
    else:
        yield from _stream_extractive(question, hits)


def _stream_ollama(question: str, hits: list[Hit], history: list[dict]) -> Iterator[str]:
    """Stream from Ollama's /api/chat (newline-delimited JSON)."""
    model = settings.OLLAMA_MODEL
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                     {"role": "user", "content": build_user_turn(question, hits)}],
        "stream": True,
        # Ollama's default context (2-4K tokens) would silently truncate six passages plus history.
        "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.2},
    }
    try:
        with httpx.stream("POST", f"{settings.OLLAMA_URL}/api/chat", json=payload,
                          timeout=httpx.Timeout(300, connect=5)) as response:
            if response.status_code == 404:
                raise AnswerError(f"The Ollama model '{model}' isn't downloaded yet. Run: ollama pull {model}")
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise AnswerError(f"Ollama error: {data['error']}")
                text = data.get("message", {}).get("content", "")
                if text:
                    yield text
                if data.get("done"):
                    break
    except httpx.ConnectError as exc:
        raise AnswerError(f"Can't reach Ollama at {settings.OLLAMA_URL}. Is the Ollama app running?") from exc
    except httpx.TimeoutException as exc:
        raise AnswerError("The local model took too long to answer. Try a shorter question or a smaller model.") from exc
    except httpx.HTTPStatusError as exc:
        raise AnswerError(f"Ollama returned an error ({exc.response.status_code}).") from exc


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"


def _gemini_error(status: int, body: bytes) -> AnswerError:
    try:
        detail = json.loads(body).get("error", {})
    except ValueError:
        detail = {}
    reason = json.dumps(detail.get("details", "")) + detail.get("status", "")
    log.error("Gemini API error %s: %s", status, detail.get("message", body[:300]))
    if "API_KEY_INVALID" in reason or status in (401, 403):
        return AnswerError("The Gemini API key was rejected. Check GEMINI_API_KEY in backend/.env.")
    if status == 429:
        return AnswerError("Gemini's free-tier rate limit was reached. Wait a minute and try again.")
    if status == 404:
        return AnswerError(f"Gemini doesn't recognise the model '{settings.GEMINI_MODEL}'. Check GEMINI_MODEL.")
    return AnswerError(f"Gemini returned an error ({status}). Please try again.")


def _stream_gemini(question: str, hits: list[Hit], history: list[dict]) -> Iterator[str]:
    """Stream from the Gemini REST API (Server-Sent Events). Gemini calls the assistant role "model"."""
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in history]
    contents.append({"role": "user", "parts": [{"text": build_user_turn(question, hits)}]})
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": settings.LLM_MAX_TOKENS},
    }
    finish = None
    try:
        with httpx.stream("POST", GEMINI_URL.format(model=settings.GEMINI_MODEL), json=payload,
                          headers={"x-goog-api-key": settings.GEMINI_API_KEY},
                          timeout=httpx.Timeout(120, connect=10)) as response:
            if response.status_code != 200:
                raise _gemini_error(response.status_code, response.read())
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = json.loads(line[5:])
                if data.get("promptFeedback", {}).get("blockReason"):
                    yield "_Gemini declined to answer this request._"
                    return
                for candidate in data.get("candidates", [])[:1]:
                    for part in candidate.get("content", {}).get("parts", []):
                        if part.get("text") and not part.get("thought"):
                            yield part["text"]
                    finish = candidate.get("finishReason") or finish
    except httpx.ConnectError as exc:
        raise AnswerError("Couldn't reach the Gemini API. Check your internet connection.") from exc
    except httpx.TimeoutException as exc:
        raise AnswerError("Gemini took too long to answer. Please try again.") from exc
    if finish == "MAX_TOKENS":
        yield "\n\n_(Answer truncated: it hit the length limit.)_"
    elif finish in {"SAFETY", "RECITATION", "PROHIBITED_CONTENT"}:
        yield "\n\n_Gemini stopped this answer early (content filter)._"


def _stream_claude(question: str, hits: list[Hit], history: list[dict]) -> Iterator[str]:
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    messages = [*history, {"role": "user", "content": build_user_turn(question, hits)}]
    try:
        with client.messages.stream(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            output_config={"effort": settings.LLM_EFFORT},
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            yield "\n\n_The model declined to answer this request._"
        elif final.stop_reason == "max_tokens":
            yield "\n\n_(Answer truncated: it hit the length limit.)_"
    except anthropic.RateLimitError as exc:
        raise AnswerError("The language model is rate-limited right now. Please try again in a moment.") from exc
    except anthropic.APIStatusError as exc:
        log.error("Claude API error %s: %s", exc.status_code, exc.message)
        raise AnswerError("The language model returned an error. Please try again.") from exc
    except anthropic.APIConnectionError as exc:
        raise AnswerError("Couldn't reach the language model. Check the server's network connection.") from exc


def _stream_extractive(question: str, hits: list[Hit], max_sentences: int = 3, pool: int = 4) -> Iterator[str]:
    """No LLM configured: quote the sentences that best match the question, each cited.

    Sentences are scored across the top passages together, so an irrelevant
    passage that merely ranked third doesn't earn a bullet.
    """
    terms = set(tokenize(question))
    candidates: list[tuple[int, int, int, str]] = []  # (-score, source n, position, sentence)
    seen: set[str] = set()  # overlapping chunks repeat sentences: quote each once
    for n, hit in enumerate(hits[:pool], start=1):
        for pos, sentence in enumerate(s.strip() for s in _SENTENCES.split(hit.text)):
            score = len(terms & set(tokenize(sentence)))
            if len(sentence) > 25 and score and sentence not in seen:
                seen.add(sentence)
                candidates.append((-score, n, pos, sentence))
    best = sorted(candidates)[:max_sentences]
    top_score = -best[0][0] if best else 0
    if not best:  # nothing overlaps lexically: fall back to the top passage's opening
        best = [(0, 1, 0, _SENTENCES.split(hits[0].text)[0])]
    best.sort(key=lambda c: (c[1], c[2]))  # read in document order

    # Word matching can't answer questions that need understanding ("whose resume is this?").
    # If the best sentence matches at most half of the question's key words, say so instead of
    # presenting a weak match as an answer.
    if top_score * 2 <= max(len(terms), 1):
        intro = ("_No language model is configured, and I couldn't find a sentence that directly answers this. "
                 "Without an LLM, DocuMind can only match words, so questions that need understanding "
                 "need a language model (a free local Ollama model, or Claude). These are the closest passages:_")
    else:
        intro = "_No language model is configured, so here are the most relevant sentences from your documents:_"
    lines = [intro, ""]
    lines += [f"- {sentence} [{n}]" for _, n, _, sentence in best]
    text = "\n".join(lines)
    for i in range(0, len(text), 24):  # stream in small pieces so the UI behaves like the LLM path
        yield text[i:i + 24]
        time.sleep(0.012)
