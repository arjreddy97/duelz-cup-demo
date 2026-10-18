"""Model access with token/dollar metering.

`get_model()` returns the real Gemini client. Only when DEMO_FAKE_MODEL=1 does it
return the scripted stand-in from devtools/ (used for local testing; devtools/ is
not shipped in the container image).
"""
import asyncio
from dataclasses import asdict, dataclass

from . import config

# One action per model turn. Every field except `action` is optional.
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "action": {"type": "string",
                   "enum": ["list_files", "read_file", "run_tests", "replace", "write_file", "finish"]},
        "path": {"type": "string"},
        "start_line": {"type": "integer"},
        "end_line": {"type": "integer"},
        "tests": {"type": "array", "items": {"type": "string"}},
        "old": {"type": "string"},
        "new": {"type": "string"},
        "content": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["action"],
}


@dataclass
class Usage:
    prompt: int = 0   # all prompt tokens sent this call, cached ones included
    cached: int = 0   # part of `prompt` served from Gemini's (implicit) cache
    output: int = 0   # response + thinking tokens


@dataclass
class Meter:
    calls: int = 0
    input_tokens: int = 0      # prompt tokens, not counting cached ones
    cached_tokens: int = 0
    output_tokens: int = 0     # response + thinking tokens
    model_seconds: float = 0.0
    max_prompt_tokens: int = 0

    @property
    def cost_usd(self):
        return (self.input_tokens * config.PRICE_INPUT
                + self.cached_tokens * config.PRICE_CACHED
                + self.output_tokens * config.PRICE_OUTPUT) / 1e6

    def add(self, usage, seconds):
        self.calls += 1
        self.model_seconds += seconds
        if usage is None:
            return
        cached = min(usage.cached, usage.prompt)
        self.cached_tokens += cached
        self.input_tokens += usage.prompt - cached
        self.output_tokens += usage.output
        self.max_prompt_tokens = max(self.max_prompt_tokens, usage.prompt)

    def snapshot(self):
        d = asdict(self)
        d["cost_usd"] = round(self.cost_usd, 6)
        d["model_seconds"] = round(self.model_seconds, 2)
        return d


class GeminiModel:
    """The real thing: google-genai, JSON output constrained to ACTION_SCHEMA."""

    name = config.MODEL

    def __init__(self):
        from google import genai  # imported lazily so fake-model runs never touch it
        from google.genai import types
        self._types = types
        self._client = genai.Client(api_key=config.api_key())

    async def generate(self, contents, system):
        """contents: list of {"role": "user"|"model", "text"}. Returns (text, Usage)."""
        t = self._types
        cfg = t.GenerateContentConfig(
            system_instruction=system,
            thinking_config=t.ThinkingConfig(thinking_level=config.THINKING_LEVEL),
            response_mime_type="application/json",
            response_json_schema=ACTION_SCHEMA,
            max_output_tokens=config.MAX_OUTPUT_TOKENS,
        )
        turns = [t.Content(role=c["role"], parts=[t.Part(text=c["text"])]) for c in contents]
        resp = await asyncio.wait_for(
            self._client.aio.models.generate_content(model=config.MODEL, contents=turns, config=cfg),
            timeout=config.CALL_TIMEOUT_SECONDS)
        u = resp.usage_metadata
        usage = Usage()
        if u is not None:
            usage = Usage(prompt=u.prompt_token_count or 0,
                          cached=u.cached_content_token_count or 0,
                          output=(u.candidates_token_count or 0) + (u.thoughts_token_count or 0))
        try:
            text = resp.text or ""
        except Exception:  # e.g. blocked or empty candidate
            text = ""
        return text, usage


_model = None


def get_model():
    global _model
    if config.FAKE_MODEL:
        try:
            from devtools.fake_model import FakeModel
        except ImportError as exc:  # devtools/ is not in the production image
            raise RuntimeError("DEMO_FAKE_MODEL=1 but devtools/ is not available") from exc
        return FakeModel.from_env()
    if _model is None:
        _model = GeminiModel()
    return _model
