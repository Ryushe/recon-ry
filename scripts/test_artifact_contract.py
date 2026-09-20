#!/usr/bin/env python3
"""Offline artifact presentation checks; stages are replaced with local writes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ArtifactSummaryTests(unittest.TestCase):
    def test_project_and_url_only_summaries_include_host_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, ROOT=str(ROOT), FIXTURE=tmp)
            for mode in ("project", "url-only"):
                with self.subTest(mode=mode):
                    script = '''
source "$ROOT/src/stages.sh"
log_info() { :; }
get_profile_stages() { printf '%s\\n' fixture; }
reorder_stages_eyewitness_last() { printf '%s\\n' "$1"; }
execute_stage() {
    printf '%s\\n' root.example.test offline.example.test > "$2/hosts.txt"
    printf '%s\\n' https://root.example.test > "$2/alive.txt"
}
'''
                    if mode == "project":
                        script += 'execute_stage fixture "$FIXTURE"; show_results_summary "$FIXTURE"'
                    else:
                        script += 'run_recon_url_only https://root.example.test fixture'
                    result = subprocess.run(["bash", "-c", script], env=env,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if mode == "project":
                        self.assertRegex(result.stdout, r"hosts\.txt\s*: 2 entries")
                        self.assertRegex(result.stdout, r"alive\.txt\s*: 1 entries")
                    else:
                        self.assertIn("=== hosts.txt ===\nroot.example.test\noffline.example.test", result.stdout)
                        self.assertIn("=== alive.txt ===\nhttps://root.example.test", result.stdout)


if __name__ == "__main__":
    unittest.main()
