import json
import logging
import config

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper over Anthropic / OpenAI that returns parsed JSON."""

    def __init__(self):
        self.provider = config.LLM_PROVIDER
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        elif self.provider == "openai":
            import openai
            self._client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {self.provider!r}")
        return self._client

    def chat(self, system: str, user: str, model: str, max_tokens: int = 512) -> dict | None:
        """Send a chat request, return parsed JSON dict or None on error."""
        client = self._get_client()
        try:
            if self.provider == "anthropic":
                msg = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                raw = msg.content[0].text
            else:
                resp = client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                raw = resp.choices[0].message.content

            return self._parse_json(raw)
        except Exception as e:
            logger.error("LLM error (%s): %s", model, e)
            return None

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error: %s | raw: %r", e, text[:200])
            return None
