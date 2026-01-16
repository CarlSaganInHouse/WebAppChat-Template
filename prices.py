# prices.py
# --- Catalog of models you want to expose in the UI ---
# Format: (id, label, $/M input, $/M output, streaming_supported, category)

MODEL_CATALOG = [
    # OpenAI API Models
    ("gpt-5-mini",             "GPT-5 Mini",                          0.25,       2.00,       False,  "openai"),
    ("gpt-5",                  "GPT-5 (Reasoning)",                   1.25,       10.00,      False,  "openai"),
    ("gpt-5-nano",             "GPT-5 Nano",                          0.05,       0.40,       True,   "openai"),
    ("gpt-4o",                 "GPT-4o (Latest)",                     2.50,       10.00,      False,  "openai"),
    ("gpt-4o-mini",            "GPT-4o Mini",                         0.15,       0.60,       False,  "openai"),
    ("gpt-4-turbo-2024-04-09", "GPT-4 Turbo",                         10.00,      30.00,      False,  "openai"),
    ("gpt-3.5-turbo",          "GPT-3.5 Turbo",                       0.50,       1.50,       False,  "openai"),

    # Anthropic Claude API Models (Latest)
    ("claude-sonnet-4-5-20250929",  "Claude Sonnet 4.5 (Latest)",     3.00,       15.00,      True,   "anthropic"),
    ("claude-haiku-4-5-20251001",   "Claude Haiku 4.5",               1.00,       5.00,       True,   "anthropic"),
    ("claude-opus-4-1-20250805",    "Claude Opus 4.1",                15.00,      75.00,      True,   "anthropic"),

    # Anthropic Claude API Models (Legacy)
    ("claude-sonnet-4-20250514",    "Claude Sonnet 4",                3.00,       15.00,      True,   "anthropic"),
    ("claude-3-7-sonnet-20250219",  "Claude 3.7 Sonnet",              3.00,       15.00,      True,   "anthropic"),
    ("claude-3-5-haiku-20241022",   "Claude 3.5 Haiku",               0.80,       4.00,       True,   "anthropic"),

    # Claude Code CLI (Uses Max subscription, not API billing)
    ("claude-code-opus",            "Claude Code Opus",               0.00,       0.00,       False,  "anthropic-cli"),
    ("claude-code-sonnet",          "Claude Code Sonnet",             0.00,       0.00,       False,  "anthropic-cli"),
    ("claude-code-haiku",           "Claude Code Haiku",              0.00,       0.00,       False,  "anthropic-cli"),

    # OpenAI Codex CLI (Uses ChatGPT Plus/Pro subscription, not API billing)
    ("codex-gpt52",                 "Codex GPT-5.2 (Latest)",         0.00,       0.00,       False,  "openai-cli"),
    ("codex-gpt51-max",             "Codex GPT-5.1 Max",              0.00,       0.00,       False,  "openai-cli"),
    ("codex-gpt51-mini",            "Codex GPT-5.1 Mini",             0.00,       0.00,       False,  "openai-cli"),

    # Google Gemini CLI (Uses Google Login - free tier: 60 req/min, 1000/day)
    ("gemini-cli-3-pro",            "Gemini 3 Pro Preview",           0.00,       0.00,       False,  "google-cli"),
    ("gemini-cli-3-flash",          "Gemini 3 Flash Preview",         0.00,       0.00,       False,  "google-cli"),
    ("gemini-cli-25-pro",           "Gemini 2.5 Pro",                 0.00,       0.00,       False,  "google-cli"),
    ("gemini-cli-25-flash",         "Gemini 2.5 Flash",               0.00,       0.00,       False,  "google-cli"),
    ("gemini-cli-25-flash-lite",    "Gemini 2.5 Flash Lite",          0.00,       0.00,       False,  "google-cli"),

    # Local Ollama Models - With Native Tool Calling
    ("qwen3:30b",              "Qwen 3 30B MoE (54 t/s)",             0.00,       0.00,       True,   "local"),
    ("qwen3:32b",              "Qwen 3 32B (Best Quality)",           0.00,       0.00,       True,   "local"),
    ("qwen3:14b",              "Qwen 3 14B (21 t/s)",                 0.00,       0.00,       True,   "local"),
    ("qwen3:8b",               "Qwen 3 8B (37 t/s)",                  0.00,       0.00,       True,   "local"),
    ("qwen3:4b-instruct-2507-q4_K_M", "Qwen 3 4B (64 t/s)",           0.00,       0.00,       True,   "local"),
    ("qwen2.5:14b",            "Qwen 2.5 14B (Tool Calling)",         0.00,       0.00,       True,   "local"),
    ("qwen2.5:7b",             "Qwen 2.5 7B (Tool Calling)",          0.00,       0.00,       True,   "local"),
    ("llama3.2:3b",            "Llama 3.2 3B (Tool Calling)",         0.00,       0.00,       True,   "local"),

    # Local Ollama Models - MCP Filesystem
    ("mistral:7b-instruct-q4_0", "Mistral 7B Instruct",               0.00,       0.00,       True,   "local"),
    ("codestral:22b",          "Codestral 22B (Code)",                0.00,       0.00,       True,   "local"),

    # Local Ollama Models - Standard
    ("phi3:mini",              "Phi-3 Mini",                          0.00,       0.00,       True,   "local"),
    ("tinyllama:latest",       "TinyLlama 1.1B (Fast)",               0.00,       0.00,       True,   "local"),
]

# Category labels for UI grouping
CATEGORY_LABELS = {
    "anthropic": "Anthropic Claude (API)",
    "anthropic-cli": "Claude Code CLI (Max Sub)",
    "openai": "OpenAI (API)",
    "openai-cli": "Codex CLI (ChatGPT Sub)",
    "google-cli": "Gemini CLI (Free Tier)",
    "local": "Local Models (Ollama)",
}

# Category display order
CATEGORY_ORDER = ["anthropic-cli", "openai-cli", "google-cli", "anthropic", "openai", "local"]

DEFAULT_MODEL = "claude-code-sonnet"

def allowed_models():
    return [m[0] for m in MODEL_CATALOG]

def get_model_meta(model_id: str):
    for mid, label, pin, pout, can_stream, category in MODEL_CATALOG:
        if mid == model_id:
            return {
                "id": mid,
                "label": label,
                "in": pin,
                "out": pout,
                "stream": can_stream,
                "category": category
            }
    # fallback to default
    return get_model_meta(DEFAULT_MODEL)

def get_models_by_category():
    """Get models organized by category for grouped dropdown."""
    from collections import OrderedDict

    # Initialize categories in display order
    categories = OrderedDict()
    for cat in CATEGORY_ORDER:
        categories[cat] = {
            "label": CATEGORY_LABELS.get(cat, cat),
            "models": []
        }

    # Populate models
    for mid, label, pin, pout, can_stream, category in MODEL_CATALOG:
        if category in categories:
            categories[category]["models"].append({
                "id": mid,
                "label": label,
                "in": pin,
                "out": pout,
                "stream": can_stream,
                "category": category
            })

    # Remove empty categories
    return {k: v for k, v in categories.items() if v["models"]}

def prices_for(model_id: str):
    m = get_model_meta(model_id)
    return m["in"], m["out"]

def streaming_supported(model_id: str):
    m = get_model_meta(model_id)
    return m["stream"]

def is_local_model(model_id: str):
    """Check if a model is local (Ollama) vs remote (OpenAI/Anthropic)"""
    local_models = [
        "qwen3:30b", "qwen3:32b", "qwen3:14b", "qwen3:8b",
        "qwen3:4b-instruct-2507-q4_K_M",
        "qwen2.5:14b", "qwen2.5:7b", "llama3.2:3b",
        "mistral:7b-instruct-q4_0", "codestral:22b",
        "phi3:mini", "tinyllama:latest",
    ]
    return model_id in local_models


def is_native_tool_model(model_id: str):
    """Check if model supports Ollama's native tool calling API."""
    native_tool_models = [
        "qwen3:30b", "qwen3:32b", "qwen3:14b", "qwen3:8b",
        "qwen3:4b-instruct-2507-q4_K_M",
        "qwen2.5:14b", "qwen2.5:7b", "llama3.2:3b",
    ]
    return model_id in native_tool_models

def is_claude_model(model_id: str):
    """Check if a model is an Anthropic Claude API model"""
    return model_id.startswith("claude-") and not model_id.startswith("claude-code-")

def is_claude_code(model_id: str):
    """Check if this is a Claude Code CLI model (uses Max subscription)"""
    return model_id.startswith("claude-code-")

def get_claude_code_model(model_id: str):
    """Extract the model tier (opus/sonnet/haiku) from claude-code-* model ID"""
    if model_id == "claude-code-opus":
        return "opus"
    elif model_id == "claude-code-sonnet":
        return "sonnet"
    elif model_id == "claude-code-haiku":
        return "haiku"
    return "sonnet"  # Default fallback

def is_codex(model_id: str):
    """Check if this is a Codex CLI model (uses ChatGPT Plus/Pro subscription)"""
    return model_id.startswith("codex-")

def get_codex_model(model_id: str):
    """Extract the Codex model name from model ID"""
    mapping = {
        "codex-gpt52": "gpt-5.2-codex",
        "codex-gpt51-max": "gpt-5.1-codex-max",
        "codex-gpt51-mini": "gpt-5.1-codex-mini",
    }
    return mapping.get(model_id, "gpt-5.2-codex")

def is_gemini_cli(model_id: str):
    """Check if this is a Gemini CLI model (uses Google Login free tier)"""
    return model_id.startswith("gemini-cli-")

def get_gemini_cli_model(model_id: str):
    """Extract the Gemini model name from model ID"""
    mapping = {
        "gemini-cli-3-pro": "gemini-3-pro-preview",
        "gemini-cli-3-flash": "gemini-3-flash-preview",
        "gemini-cli-25-pro": "gemini-2.5-pro",
        "gemini-cli-25-flash": "gemini-2.5-flash",
        "gemini-cli-25-flash-lite": "gemini-2.5-flash-lite",
    }
    return mapping.get(model_id, "gemini-2.5-flash")

def is_mcp_enabled_model(model_id: str):
    """Check if model should use MCP prompt-based filesystem capabilities."""
    from config import settings

    mcp_capable_models = [
        "mistral:7b-instruct-q4_0",
        "codestral:22b",
    ]

    if not getattr(settings, 'mcp_enabled', True):
        return False

    return model_id in mcp_capable_models

def get_model_tier(model_id: str):
    """Get the performance tier for local models."""
    tiers = {
        "qwen3:30b": "excellent",
        "qwen3:32b": "excellent",
        "qwen3:14b": "good",
        "qwen3:8b": "good",
        "qwen3:4b-instruct-2507-q4_K_M": "good",
        "qwen2.5:14b": "excellent",
        "qwen2.5:7b": "excellent",
        "llama3.2:3b": "good",
        "mistral:7b-instruct-q4_0": "good",
        "codestral:22b": "good",
    }
    return tiers.get(model_id, "unknown")

# Backwards compatibility alias
def get_mcp_model_tier(model_id: str):
    """Deprecated: Use get_model_tier instead."""
    return get_model_tier(model_id)

def get_provider_type(model_id: str):
    """
    Determine which provider to use for a given model.

    Returns:
        'claude_code'  - Claude Code CLI (Max subscription, agentic)
        'codex'        - OpenAI Codex CLI (ChatGPT Plus/Pro subscription)
        'gemini_cli'   - Google Gemini CLI (Google Login free tier)
        'ollama_tools' - Native Ollama tool calling (qwen2.5, llama3.2)
        'ollama_mcp'   - MCP prompt-based tool calling (mistral, codestral)
        'ollama'       - Basic Ollama chat (phi3, tinyllama)
        'anthropic'    - Anthropic Claude models
        'openai'       - OpenAI models (default)
    """
    if is_claude_code(model_id):
        return 'claude_code'
    elif is_codex(model_id):
        return 'codex'
    elif is_gemini_cli(model_id):
        return 'gemini_cli'
    elif is_native_tool_model(model_id):
        return 'ollama_tools'
    elif is_mcp_enabled_model(model_id):
        return 'ollama_mcp'
    elif is_local_model(model_id):
        return 'ollama'
    elif is_claude_model(model_id):
        return 'anthropic'
    else:
        return 'openai'
