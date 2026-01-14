"""
Constants for the review system.
"""

# Model to API key name mapping for validation and recovery
MODEL_TO_API_KEY = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "codex": "OPENAI_API_KEY",  # Codex uses OpenAI
    "grok": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
