#!/usr/bin/env python3
"""Offline regressions from independent review; never launches a real scanner."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import incremental_eyewitness as eye
import recon_enrichment as enrichment
import test_defensive_boundaries as boundaries

ROOT = Path(__file__).resolve().parents[1]
MOCK_TOOL_SETUP = '''
is_tool_enabled() { return 0; }
check_tool_exists() { return 0; }
get_rate_limit() { printf 1; }
get_install_info() { :; }
get_payload_command() { :; }
get_tool_info() {
 if [[ "$2" == command ]]; then printf '%s' 'printf "https://example.test/partial\\n" > {{OUTPUT}}; sleep 2'; fi
}
TOOL_TIMEOUT=1
printf '%s\\n' https://example.test > "$TEST_DIR/input"
'''


class ReviewRegressions(unittest.TestCase):
    shell = boundaries.ShellTests.shell

    def test_missing_scope_paths_abort_before_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if not k.startswith("RECON_RY_")}
            for option in ("--scope-file", "--out-scope-file"):
                result = subprocess.run(
                    ["bash", str(ROOT / "main.sh"), "recon", "--dry-run", "--project", d + "/project",
                     "--exact-urls", "--url", "https://example.test", option, d + "/missing-parent/scope"],
                    capture_output=True, text=True, env=env, timeout=30,
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotIn("DRY RUN MODE", result.stderr)

    def test_actual_parallel_timeout_receipts_and_raw_evidence(self):
        self.shell(MOCK_TOOL_SETUP + '''
rc=0
run_tools_parallel "fixture:$TEST_DIR/input:$TEST_DIR/one.txt::" "fixture:$TEST_DIR/input:$TEST_DIR/two.txt::" || rc=$?
[[ $rc -eq 124 ]]
python3 - "$TEST_DIR" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
rows=list((root/'tool-status').glob('result.*'))
assert len(rows)==2
assert all('exit_code\\t124\\n' in p.read_text() for p in rows)
raw=list((root/'.partials').glob('evidence.*'))
assert len(raw)==2
assert all('https://example.test/partial' in p.read_text() for p in raw)
PY
''')

    def test_direct_verbose_timeout_is_captured_under_errexit(self):
        self.shell(MOCK_TOOL_SETUP + '''
PROJECT_DIR=""
VERBOSE=2; logger_init 2
rc=0; run_tool_direct fixture "$TEST_DIR/input" "$TEST_DIR/result.txt" '' '' || rc=$?
[[ $rc -eq 124 ]]
[[ -d "$TEST_DIR/tool-status" ]]
''')

    def test_archive_and_receipt_failure_preserve_timeout(self):
        output = self.shell(MOCK_TOOL_SETUP + '''
printf blocked > "$TEST_DIR/.partials"
printf blocked > "$TEST_DIR/tool-status"
rc=0; run_tool_with_anew fixture "$TEST_DIR/input" "$TEST_DIR/result.txt" '' '' || rc=$?
[[ $rc -eq 124 ]]
[[ $(< "$TEST_DIR/result.txt") == https://example.test/partial ]]
''')
        self.assertIn("unable to persist receipt", output)
        self.assertIn("cannot create partial evidence archive", output)

    def test_ffuf_timeout_before_output_exists(self):
        self.shell('''execute_tool() { return 124; }
rc=0; run_tool_with_anew ffuf '' "$TEST_DIR/dirs.txt" '' '' || rc=$?
[[ $rc -eq 124 ]]
python3 - "$TEST_DIR/.partials" <<'PY'
from pathlib import Path
import sys
rows=list(Path(sys.argv[1]).glob('evidence.*'))
assert len(rows)==1 and rows[0].stat().st_size==0
PY
''')

    def test_preflight_outcomes_have_distinct_receipts(self):
        self.shell('''is_tool_enabled() { return 0; }
check_tool_exists() { return 1; }
printf '%s\\n' https://example.test > "$TEST_DIR/input"
rc=0; execute_tool fixture "$TEST_DIR/input" "$TEST_DIR/result.txt" '' '' || rc=$?
[[ $rc -eq 1 ]]
printf '%s\\n' https://evil.test > "$TEST_DIR/unauthorized"
rc=0; execute_tool fixture "$TEST_DIR/unauthorized" "$TEST_DIR/result.txt" '' '' || rc=$?
[[ $rc -eq 2 ]]
is_tool_enabled() { return 1; }
execute_tool fixture "$TEST_DIR/input" "$TEST_DIR/result.txt" '' ''
python3 - "$TEST_DIR/tool-status" <<'PY'
from pathlib import Path
import sys
outcomes={dict(line.split('\t',1) for line in p.read_text().splitlines())['outcome'] for p in Path(sys.argv[1]).glob('result.*')}
assert outcomes=={'missing','scope_blocked','skipped'}, outcomes
PY
''')

    def test_saved_eyewitness_chunk_dispatch_is_rechecked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "saved-chunk.txt"
            source.write_text("https://example.test/\nhttps://evil.test/\n")
            allow = root / "scope"
            allow.write_text("example.test\n")
            chunk = eye.Chunk("chunk_1", 1, str(source), str(root / "old-work"), status="failed", urls=2)
            state = eye.RunState(str(source), str(root / "store"), "run1", str(root / "run"), 2, "fixture", chunks=[chunk])
            args = argparse.Namespace(db_root=str(root / "db"), python=sys.executable, eyewitness=root / "fake-eye.py", timeout=1, threads=1, max_retries=0, results=1, keep_work=True)
            captured = []
            real_run = subprocess.run

            def offline_run(command, **kwargs):
                if command[1] == str(args.eyewitness):
                    captured.append(Path(command[command.index("-f") + 1]).read_text())
                    return SimpleNamespace(returncode=1)
                return real_run(command, **kwargs)

            env = {k: v for k, v in os.environ.items() if not k.startswith("RECON_RY_")}
            env["RECON_RY_SCOPE_FILE"] = str(allow)
            with patch.dict(os.environ, env, clear=True), patch.object(eye.subprocess, "run", side_effect=offline_run):
                self.assertFalse(eye.run_chunk(chunk, args, root / "store", root / "run", root / "state.json", state))
                self.assertEqual(captured, ["https://example.test/\n"])
                self.assertIn("https://evil.test/", source.read_text())
                allow.write_text("other.test\n")
                self.assertFalse(eye.run_chunk(chunk, args, root / "store", root / "run", root / "state.json", state))
                self.assertEqual(chunk.status, "blocked")
                self.assertEqual(len(captured), 1)

    def test_ip_and_legacy_host_parsing(self):
        self.assertEqual(enrichment.extract_host("2001:db8::1"), "2001:db8::1")
        self.assertEqual(enrichment.extract_host("https://[2001:db8::1]:8443/"), "2001:db8::1")
        self.assertEqual(enrichment.load_hosts_from_host_port(["example.test", "api.example.test:443", "[2001:db8::1]:8443"]), {"example.test", "api.example.test", "2001:db8::1"})

    def test_report_cache_invalidates_when_source_base_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest = root / "requests.jsonl"
            manifest.write_text(json.dumps({"url": "https://example.test/"}) + "\n")
            db = root / "cache.sqlite"
            self.assertFalse(eye.build_report_cache(manifest, db, root / "source-a")["cached"])
            self.assertTrue(eye.build_report_cache(manifest, db, root / "source-a")["cached"])
            self.assertFalse(eye.build_report_cache(manifest, db, root / "source-b")["cached"])

    def test_yaml_keys_unique_and_profile_defaults_match(self):
        import yaml
        class UniqueLoader(yaml.SafeLoader):
            pass
        def mapping(loader, node, deep=False):
            result = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                if key in result:
                    raise ValueError("duplicate YAML key: " + str(key))
                result[key] = loader.construct_object(value_node, deep=deep)
            return result
        UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        paths = sorted((ROOT / "config").glob("*.yaml")) + sorted((ROOT / "config/defaults").glob("*.yaml"))
        for path in paths:
            yaml.load(path.read_text(), Loader=UniqueLoader)
        current = yaml.safe_load((ROOT / "config/profiles.yaml").read_text())["profiles"]
        defaults = yaml.safe_load((ROOT / "config/defaults/profiles.yaml").read_text())["profiles"]
        for profile in ("snap", "exact-urls", "exact-urls-header"):
            self.assertEqual(current[profile]["stages"], defaults[profile]["stages"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
