"""Provider dispatch — Ollama and LM Studio expose the same client interface:
ping, list_models, native_context_length, effective_num_ctx, chat_once,
chat_stream, pull_model. agent.py / compact.py / ui.py go through here so
they never import a specific backend directly.
"""
from __future__ import annotations

from . import lmstudio_client, ollama_client

PROVIDERS = ("ollama", "lmstudio")
LABELS = {"ollama": "Ollama", "lmstudio": "LM Studio"}
DEFAULT_HOSTS = {"ollama": "http://127.0.0.1:11434", "lmstudio": "http://127.0.0.1:1234"}


def client_for(provider: str):
    return lmstudio_client if provider == "lmstudio" else ollama_client


def default_host(provider: str) -> str:
    return DEFAULT_HOSTS.get(provider, DEFAULT_HOSTS["ollama"])


def host_for(settings) -> str:
    """The configured host for settings.provider."""
    if settings.provider == "lmstudio":
        return settings.lmstudio_host
    return settings.ollama_host


def label_for(provider: str) -> str:
    return LABELS.get(provider, "Ollama")
