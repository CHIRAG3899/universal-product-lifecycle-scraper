#!/usr/bin/env python3
"""
Interactive Universal AI Provider Setup & Validation Tool.
Helps users configure, test, and persist API keys for:
  - Google Gemini (gemini-3.5-flash-lite, gemini-3.5-flash)
  - OpenAI (gpt-4o, gpt-4o-mini)
  - Anthropic Claude (claude-3-5-sonnet, claude-3-5-haiku)
  - Microsoft Azure OpenAI (azure/<deployment>)
  - Amazon AWS Bedrock (bedrock/<model-id>)
  - Local / Ollama / OpenRouter (OpenAI-compatible)
"""

import os
import sys
from pathlib import Path

# Fix Windows console encoding for UTF-8 output
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from scraper.gemini_extractor import UniversalAIExtractor
from scraper.providers import DEFAULT_MODELS, normalize_provider_name


def print_banner():
    print("=" * 76)
    print("  GOOGLE GEMINI API KEY SETUP & UNIVERSAL MULTI-PROVIDER AI CONFIGURATOR")
    print("  Enterprise Multi-Vendor Lifecycle AI Scraper (OT / IoT / IT)")
    print("=" * 76)
    print("\n[PLUG-AND-PLAY AI PROVIDERS]")
    print("  1. Google Gemini   : Free tier at https://aistudio.google.com/app/apikey")
    print("  2. OpenAI          : https://platform.openai.com/api-keys (gpt-4o, gpt-4o-mini)")
    print("  3. Anthropic Claude: https://console.anthropic.com/ (claude-3-5-sonnet, haiku)")
    print("  4. Azure OpenAI    : Microsoft Azure Cognitive Services deployment")
    print("  5. AWS Bedrock     : Amazon Bedrock Anthropic/Titan/Llama foundation models")
    print("  6. Ollama / Local  : Zero cloud dependency, 100% on-premise execution\n")
    print("-" * 76)


def test_and_save_key(
    api_key: str,
    model_name: str = "gemini-3.5-flash-lite",
    provider: str = "gemini",
    api_base: str = "",
) -> bool:
    provider = normalize_provider_name(provider)
    model = model_name or DEFAULT_MODELS.get(provider, "gemini-3.5-flash-lite")
    api_key = api_key.strip()

    print(f"\n[*] Testing provider '{provider.upper()}' with model '{model}'...")
    extractor = UniversalAIExtractor(
        provider=provider,
        api_key=api_key,
        model_name=model,
        api_base=api_base,
    )
    success, message = extractor.test_connection()

    if success:
        resolved_model = extractor.model_name
        print(f"\n[SUCCESS] {provider.upper()} API connection verified!")
        print(f"  Response: {message}")
        if resolved_model != model:
            print(f"  [AUTO-CONFIGURED] Resolved model: {resolved_model}")

        # Save to .env
        env_path = BASE_DIR / ".env"
        lines = []
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        env_vars_to_set = {
            "AI_PROVIDER": provider,
            "AI_MODEL": resolved_model,
        }
        if provider == "gemini":
            env_vars_to_set["GEMINI_API_KEY"] = api_key
            env_vars_to_set["GEMINI_MODEL"] = resolved_model
        elif provider == "openai":
            env_vars_to_set["OPENAI_API_KEY"] = api_key
        elif provider == "anthropic":
            env_vars_to_set["ANTHROPIC_API_KEY"] = api_key
        elif provider == "azure":
            env_vars_to_set["AZURE_OPENAI_API_KEY"] = api_key
        elif provider == "bedrock":
            env_vars_to_set["AWS_ACCESS_KEY_ID"] = api_key
        elif provider in ("ollama", "local"):
            if api_base:
                env_vars_to_set["OPENAI_BASE_URL"] = api_base

        new_lines = []
        updated_keys = set()
        for line in lines:
            line_stripped = line.strip()
            matched = False
            for k, v in env_vars_to_set.items():
                if line_stripped.startswith(f"{k}="):
                    new_lines.append(f"{k}={v}\n")
                    updated_keys.add(k)
                    matched = True
                    break
            if not matched:
                new_lines.append(line)

        for k, v in env_vars_to_set.items():
            if k not in updated_keys:
                new_lines.append(f"{k}={v}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        print(f"\n[SAVED] Configuration saved to: {env_path.name}")
        print(f"  The crawler is now configured with provider '{provider}' and model '{resolved_model}'.")
        return True
    else:
        print(f"\n[VERIFICATION FAILED: {provider.upper()}]")
        print(f"  {message}")
        return False


def main():
    print_banner()

    # CLI args support
    if len(sys.argv) > 1 and sys.argv[1].startswith("--key="):
        key = sys.argv[1].split("=", 1)[1]
        prov = "gemini"
        model = "gemini-3.5-flash-lite"
        for arg in sys.argv[2:]:
            if arg.startswith("--model="):
                model = arg.split("=", 1)[1]
        if prov != "gemini":
            test_and_save_key(key, model, provider=prov)
        else:
            test_and_save_key(key, model)
        return

    print("Select AI Provider to configure:")
    print("  [1] Google Gemini (Default free tier)")
    print("  [2] OpenAI (gpt-4o, gpt-4o-mini)")
    print("  [3] Anthropic Claude (claude-3-5-sonnet, haiku)")
    print("  [4] Microsoft Azure OpenAI")
    print("  [5] Amazon AWS Bedrock")
    print("  [6] Ollama / Local (Zero Cloud)")

    try:
        choice = input("\nEnter choice [1-6, default: 1]: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.")
        return

    provider_map = {
        "1": "gemini",
        "2": "openai",
        "3": "anthropic",
        "4": "azure",
        "5": "bedrock",
        "6": "ollama",
        "": "gemini",
    }
    selected_provider = provider_map.get(choice, "gemini")

    if selected_provider == "ollama":
        base_url = input("Enter Ollama API Base URL [default: http://localhost:11434/v1]: ").strip() or "http://localhost:11434/v1"
        model = input("Enter Ollama model [default: ollama/llama3.2]: ").strip() or "ollama/llama3.2"
        test_and_save_key("ollama_local", model, provider="ollama", api_base=base_url)
        return

    # Check for existing key
    key_env_var = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
        "bedrock": "AWS_ACCESS_KEY_ID",
    }.get(selected_provider, "GEMINI_API_KEY")

    current_key = os.getenv(key_env_var, "")
    if current_key and not current_key.startswith("your_"):
        masked = current_key[:6] + "..." + current_key[-4:]
        print(f"Current detected key for {selected_provider.upper()} ({key_env_var}): {masked}")
        test_now = input("Test current key? (Y/n): ").strip().lower()
        if test_now != "n":
            if test_and_save_key(current_key, provider=selected_provider):
                return

    try:
        user_key = input(f"\nEnter your {selected_provider.upper()} API Key (or press Ctrl+C to cancel): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.")
        return

    if not user_key:
        print("No key provided. Exiting.")
        return

    test_and_save_key(user_key, provider=selected_provider)


if __name__ == "__main__":
    main()
