"""Pytest config — ensures janitor/ is importable and AWS env is clean."""

import os
import sys
from pathlib import Path

# Make the janitor package importable when running pytest from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Moto requires *some* credentials to be set, even fake ones, when its
# internal clients are constructed. Set deterministic ones for the suite.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
# Defensive: never accidentally hit a real account if the user has a real
# AWS_ENDPOINT_URL exported.
os.environ.pop("AWS_ENDPOINT_URL", None)
