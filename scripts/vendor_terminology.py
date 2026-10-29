#!/usr/bin/env python3
"""Alias for standalone_vendor_terminology.py"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.standalone_vendor_terminology import main

if __name__ == "__main__":
    sys.exit(main())
