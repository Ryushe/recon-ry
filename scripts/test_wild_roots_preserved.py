#!/usr/bin/env python3
"""Regression: wild.txt roots must survive scope_filter_artifacts.

wild.txt holds wildcard bases with "*." stripped. Filtering it as if those were
request targets deletes them, because "*.example.com" does not match the bare
base "example.com". That silently reduced subdomain enumeration to whichever
roots happened to also be declared as exact scope entries (3 of 26 on a real
program).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WildRootsPreservedTests(unittest.TestCase):
    def _run(self, scope_text, files):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d)
            scope = proj / "scope.txt"
            scope.write_text(scope_text)
            for name, body in files.items():
                (proj / name).write_text(body)
            env = {k: v for k, v in os.environ.items() if not k.startswith("RECON_RY_")}
            env["RECON_RY_SCOPE_FILE"] = str(scope)
            script = (
                f'set -uo pipefail; SCRIPT_DIR={ROOT!s}; VERBOSE=0; '
                f'source "$SCRIPT_DIR/src/logger.sh"; source "$SCRIPT_DIR/src/scope.sh"; '
                f'scope_filter_artifacts "{proj!s}"'
            )
            proc = subprocess.run(["bash", "-c", script], env=env,
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return {name: (proj / name).read_text() for name in files}

    def test_wildcard_bases_are_not_stripped_from_wild_txt(self):
        out = self._run(
            "*.example.com\n*.other.test\n",
            {"wild.txt": "example.com\nother.test\n"},
        )
        self.assertEqual(
            sorted(out["wild.txt"].split()), ["example.com", "other.test"],
            "wild.txt roots were filtered away; subdomain_enum would lose them",
        )

    def test_other_artifacts_are_still_filtered(self):
        out = self._run(
            "*.example.com\n",
            {"hosts.txt": "https://api.example.com/a\nhttps://evil.test/b\n"},
        )
        self.assertIn("api.example.com", out["hosts.txt"])
        self.assertNotIn("evil.test", out["hosts.txt"])


if __name__ == "__main__":
    unittest.main()
