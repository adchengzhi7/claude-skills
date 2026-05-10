"""Provider 註冊 — 加新 provider 時在這裡 import 並登錄到 REGISTRY。"""
from __future__ import annotations

from .stripe_style import (
    AnthropicProvider,
    NetlifyProvider,
    SupabaseProvider,
    VercelProvider,
)

REGISTRY = {
    "vercel": VercelProvider,
    "supabase": SupabaseProvider,
    "anthropic": AnthropicProvider,
    "netlify": NetlifyProvider,
}


def get_provider(name: str):
    cls = REGISTRY.get(name.lower())
    return cls() if cls else None


def list_provider_names() -> list[str]:
    return list(REGISTRY.keys())
