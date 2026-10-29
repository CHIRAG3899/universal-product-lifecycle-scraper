#!/usr/bin/env python3
"""
Interactive Google Gemini API Key Setup & Validation Tool
Helps users configure, test, and persist their Google Gemini API Key for the AI Scraper.
"""

import os
import sys
from pathlib import Path

# Fix Windows console encoding for UTF-8 output
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from scraper.gemini_extractor import GeminiExtractor


def print_banner():
    print("=" * 72)
    print("  GOOGLE GEMINI API KEY SETUP & VALIDATOR")
    print("  Enterprise Multi-Vendor Lifecycle AI Scraper")
    print("=" * 72)
    print("\n[AI ARCHITECTURE EXPLAINED]")
    print("  1. Crawl4AI: Headless Chromium browser that renders pages, bypasses")
    print("     anti-bot/cookie banners, and extracts raw markdown & DOM structures.")
    print("     Note: Crawl4AI itself DOES NOT include an inbuilt AI model.")
    print("  2. Google Gemini (gemini-1.5-flash / 2.0-flash / 3.8-flash): The AI brain that parses")
    print("     unstructured tables, translates multi-lingual text to English,")
    print("     and maps vendor lifecycle stages into normalized UTC schemas.\n")
    print("[HOW TO GET A FREE GEMINI API KEY]")
    print("  Step 1: Open https://aistudio.google.com/app/apikey in your browser.")
    print("  Step 2: Sign in with your Google account.")
    print("  Step 3: Click 'Create API key' (free tier available).")
    print("  Step 4: Copy the key (starts with 'AIzaSy...').")
    print("-" * 72)


def test_and_save_key(api_key: str, model_name: str = "gemini-3.5-flash") -> bool:
    api_key = api_key.strip()
    if not api_key:
        print("\n[ERROR] Key cannot be empty.")
        return False

    print(f"\nTesting key with model '{model_name}'...")
    extractor = GeminiExtractor(api_key=api_key, model_name=model_name)
    success, message = extractor.test_connection()

    if success:
        resolved_model = extractor.model_name
        print("\n[SUCCESS] Google Gemini API connection verified!")
        print(f"  Response: {message}")
        if resolved_model != model_name:
            print(f"  [AUTO-CONFIGURED] Switched to active model: {resolved_model}")

        # Save to .env
        env_path = BASE_DIR / ".env"
        lines = []
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        # Update or append GEMINI_API_KEY and GEMINI_MODEL
        key_found = False
        model_found = False
        new_lines = []
        for line in lines:
            if line.strip().startswith("GEMINI_API_KEY="):
                new_lines.append(f"GEMINI_API_KEY={api_key}\n")
                key_found = True
            elif line.strip().startswith("GEMINI_MODEL="):
                new_lines.append(f"GEMINI_MODEL={resolved_model}\n")
                model_found = True
            else:
                new_lines.append(line)

        if not key_found:
            new_lines.append(f"GEMINI_API_KEY={api_key}\n")
        if not model_found:
            new_lines.append(f"GEMINI_MODEL={resolved_model}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        print(f"\n[SAVED] Configuration saved to: {env_path.name}")
        print("  The crawler now has full access to Gemini AI reasoning!")
        return True
    else:
        print("\n[VERIFICATION FAILED]")
        print(f"  {message}")
        print("  Please verify your key at https://aistudio.google.com/app/apikey")
        return False


def main():
    print_banner()

    # Check for CLI args
    if len(sys.argv) > 1 and sys.argv[1].startswith("--key="):
        key = sys.argv[1].split("=", 1)[1]
        model = "gemini-3.5-flash"
        if len(sys.argv) > 2 and sys.argv[2].startswith("--model="):
            model = sys.argv[2].split("=", 1)[1]
        test_and_save_key(key, model)
        return

    # Check if a key is already in .env
    current_key = os.getenv("GEMINI_API_KEY", "")
    if current_key and current_key != "your_gemini_api_key_here":
        masked = current_key[:6] + "..." + current_key[-4:]
        print(f"Current detected key in environment: {masked}")
        test_now = input("Test current key? (Y/n): ").strip().lower()
        if test_now != "n":
            if test_and_save_key(current_key):
                return

    # Prompt user for new key
    try:
        user_key = input("\nEnter your Google Gemini API Key (or press Ctrl+C to cancel): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.")
        return

    if not user_key:
        print("No key provided. Exiting.")
        return

    test_and_save_key(user_key)


if __name__ == "__main__":
    main()
