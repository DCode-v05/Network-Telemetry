import os
import sys

# Put the package root (Phase 4/src/python) on sys.path for all tests.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src", "python"))
