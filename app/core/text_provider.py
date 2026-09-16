"""Factory: pick which LLM writes the content (Claude or OpenAI) based on user's choice."""
from __future__ import annotations

from app import config
from app.core.claude_client import ClaudeClient
from app.core.openai_content_client import OpenAIContentClient

PROVIDER_CLAUDE = "claude"
PROVIDER_OPENAI = "openai"

PROVIDER_LABELS = {
    PROVIDER_CLAUDE: "Claude (Anthropic)",
    PROVIDER_OPENAI: "OpenAI (ChatGPT)",
}


def get_text_client(provider: str):
    settings = config.load_settings()
    if provider == PROVIDER_OPENAI:
        return OpenAIContentClient(
            config.get_secret("openai_api_key"), settings.get("openai_text_model", "gpt-4o-mini")
        )
    return ClaudeClient(config.get_secret("anthropic_api_key"), settings.get("claude_model", "claude-sonnet-5"))
