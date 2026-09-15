#!/usr/bin/env python3
"""Offline regression suite: subprocesses are shell fixtures, never scanners."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scope_filter", ROOT / "scripts/scope_filter.py")
assert spec is not None and spec.loader is not None
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


def rules(*items):
    return [scope.parse_rule(item) for item in items]


class ScopeTests(unittest.TestCase):
    def test_exact_has_no_www_or_suffix_relaxation(self):
        s = scope.Scope(rules("example.test"))
        for value in ("example.test", "https://EXAMPLE.test.:8443/a?b=1"):
            self.assertTrue(s.allows(value), value)
        for value in ("www.example.test", "example.test.evil.test", "evil-example.test", "https://example.test@evil.test/", "https://evil.test@example.test/", "https://example.test\\@evil.test/", "file://example.test/a"):
            self.assertFalse(s.allows(value), value)

    def test_exclusions_win_and_wildcard_does_not_include_apex(self):
        s = scope.Scope(rules("*.example.test", "blocked.example.test"), rules("blocked.example.test", "*.private.example.test"))
        self.assertTrue(s.allows("a.example.test"))
        for value in ("example.test", "blocked.example.test", "a.private.example.test", "example.test.evil.test"):
            self.assertFalse(s.allows(value), value)

    def test_explicit_ips_and_networks_not_dns(self):
        s = scope.Scope(rules("example.test", "192.0.2.0/28", "2001:db8::1"), rules("192.0.2.4"))
        for value in ("192.0.2.1", "https://[2001:db8::1]/"):
            self.assertTrue(s.allows(value))
        for value in ("192.0.2.4", "192.0.2.16", "198.51.100.1"):
            self.assertFalse(s.allows(value))
        self.assertFalse(scope.Scope(rules("example.test")).allows("192.0.2.1"))

    def test_invalid_rules_fail_closed(self):
        for value in ("*.192.0.2.1", "https://example.test/path", "example.test:443", "192.0.2.1/24", "*example.test", "user@example.test"):
            with self.assertRaises(ValueError, msg=value):
                scope.parse_rule(value)
        with self.assertRaises(ValueError):
            scope.Scope([])

    def test_exact_profile_intersects_explicit_scope(self):
        s = scope.Scope(rules("*.example.test"), rules("a.example.test"), "https://a.example.test/")
        self.assertFalse(s.allows("a.example.test"))
        self.assertFalse(s.allows("b.example.test"))

    def test_filter_and_crawler_regex(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "input"
            p.write_text("https://a.example.test/x\nhttps://evil.test/\nhttps://a.example.test:8443/\n")
            s = scope.Scope(rules("*.example.test"))
            self.assertEqual(scope.filter_file(s, p, p), 1)
            rx = re.compile(scope.crawl_regex(s, p))
            self.assertIsNotNone(rx.search("https://a.example.test:8443/a"))
            self.assertIsNone(rx.search("https://b.example.test/"))
            self.assertIsNone(rx.search("https://a.example.test.evil.test/"))
            self.assertIsNone(rx.search("https://a.example.test@evil.test/"))


class ShellTests(unittest.TestCase):
    def shell(self, body, scope_text="example.test\n"):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "scope").write_text(scope_text)
            env = os.environ.copy()
            for key in tuple(env):
                if key.startswith("RECON_RY_"):
                    del env[key]
            env.update(TEST_ROOT=str(ROOT), TEST_DIR=d, RECON_RY_SCOPE_FILE=str(p / "scope"))
            script = '''set -euo pipefail
SCRIPT_DIR="$TEST_ROOT"
PROJECT_DIR="$TEST_DIR"
VERBOSE=0
source "$SCRIPT_DIR/src/logger.sh"
source "$SCRIPT_DIR/src/tools.sh"
source "$SCRIPT_DIR/src/stages.sh"
''' + body
            result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout + result.stderr

    def test_input_gate_preserves_source_and_denies_dns_ips(self):
        self.shell('''printf '%s\\n' https://example.test/a https://www.example.test/b > "$PROJECT_DIR/alive.txt"
filtered=$(scope_prepare_input httpx "$PROJECT_DIR/alive.txt")
[[ $(wc -l < "$filtered") -eq 1 ]]
[[ $(wc -l < "$PROJECT_DIR/alive.txt") -eq 2 ]]
printf '%s\\n' 192.0.2.1 > "$PROJECT_DIR/ips.txt"
rc=0; scope_prepare_input naabu "$PROJECT_DIR/ips.txt" || rc=$?
[[ $rc -eq 2 ]]
''')

    def test_unscoped_run_passes_input_through_unfiltered(self):
        """Without --scope-file containment is off: input is used as-is."""
        output = self.shell('''printf '%s\\n' https://example.test/a https://evil.test/b > "$PROJECT_DIR/alive.txt"
unset RECON_RY_SCOPE_FILE
selected=$(scope_prepare_input httpx "$PROJECT_DIR/alive.txt")
[[ "$selected" == "$PROJECT_DIR/alive.txt" ]]
[[ $(wc -l < "$selected") -eq 2 ]]
''')
        self.assertIn("running unfiltered", output)

    def test_every_configured_tool_runs_without_a_scope_file(self):
        """Programs without a published scope must still run the whole pipeline.

        Each configured tool has to clear the input gate unscoped and receive
        its original input, so no stage can become unreachable just because
        --scope-file was omitted.
        """
        import yaml

        config = yaml.safe_load((ROOT / "config" / "general.yaml").read_text())
        tools = sorted(config.get("tools", {}))
        self.assertTrue(tools, "no tools configured")
        self.shell('''printf '%s\\n' https://example.test/a > "$PROJECT_DIR/in.txt"
unset RECON_RY_SCOPE_FILE
for tool in ''' + " ".join(tools) + '''; do
  selected=$(scope_prepare_input "$tool" "$PROJECT_DIR/in.txt") || { echo "blocked: $tool"; exit 1; }
  [[ "$selected" == "$PROJECT_DIR/in.txt" ]] || { echo "altered: $tool -> $selected"; exit 1; }
done
''')

    def test_katana_stays_fqdn_bounded_with_and_without_scope(self):
        """`-fs fqdn` is unconditional; only the `-cs` crawl regex needs scope."""
        scoped = self.shell('''printf '%s\\n' https://a.example.test/ > "$PROJECT_DIR/wild.txt"
printf 'ARGS:%s\\n' "$(katana_crawl_args katana "$PROJECT_DIR/wild.txt")"
''', "a.example.test\n")
        self.assertIn("-fs fqdn", scoped)
        self.assertIn("-cs ", scoped)
        self.assertIn("-dr", scoped)

        unscoped = self.shell('''printf '%s\\n' https://a.example.test/ > "$PROJECT_DIR/wild.txt"
unset RECON_RY_SCOPE_FILE
printf 'ARGS:%s\\n' "$(katana_crawl_args katana "$PROJECT_DIR/wild.txt")"
''')
        args = [l for l in unscoped.splitlines() if l.startswith("ARGS:")][0]
        self.assertEqual(args, "ARGS:-fs fqdn")

    def test_katana_crawl_args_ignores_non_crawler_tools(self):
        output = self.shell('''printf 'ARGS:[%s]\\n' "$(katana_crawl_args httpx "$PROJECT_DIR/none.txt")"
''')
        self.assertIn("ARGS:[]", output)

    def test_explicit_ip_scope_retains_port_input(self):
        self.shell('''printf '%s\\n' 192.0.2.1 198.51.100.1 > "$PROJECT_DIR/ips.txt"
filtered=$(scope_prepare_input naabu "$PROJECT_DIR/ips.txt")
[[ $(< "$filtered") == 192.0.2.1 ]]
''', "192.0.2.0/24\n")

    def test_resumed_artifacts_and_history_rechecked(self):
        self.shell('''CURRENT_HISTORY_DIR="$PROJECT_DIR/history/test"
mkdir -p "$CURRENT_HISTORY_DIR" "$PROJECT_DIR/.tmp_run"
for folder in "$PROJECT_DIR" "$PROJECT_DIR/.tmp_run" "$CURRENT_HISTORY_DIR"; do
 printf '%s\\n' https://example.test/a https://evil.test/a > "$folder/jsfiles.txt"
done
scope_filter_artifacts "$PROJECT_DIR"
for folder in "$PROJECT_DIR" "$PROJECT_DIR/.tmp_run" "$CURRENT_HISTORY_DIR"; do
 [[ $(wc -l < "$folder/jsfiles.txt") -eq 1 ]]
done
[[ -d "$PROJECT_DIR/.scope-evidence" ]]
''')

    def test_timeout_preserves_evidence_and_receipt(self):
        self.shell('''is_tool_enabled() { return 0; }
check_tool_exists() { return 0; }
get_rate_limit() { printf 1; }
get_install_info() { :; }
get_payload_command() { :; }
get_tool_info() {
 if [[ "$2" == command ]]; then printf '%s' 'printf "https://example.test/partial\\n" > {{OUTPUT}}; sleep 2'; fi
}
TOOL_TIMEOUT=1
printf '%s\\n' https://example.test > "$PROJECT_DIR/input"
rc=0; run_tool_with_anew fixture "$PROJECT_DIR/input" "$PROJECT_DIR/alive.txt" '' '' || rc=$?
[[ $rc -eq 124 ]]
[[ $(< "$PROJECT_DIR/alive.txt") == https://example.test/partial ]]
python3 - "$PROJECT_DIR/tool-status" <<'PY'
from pathlib import Path
import sys
rows = list(Path(sys.argv[1]).glob('result.*'))
assert len(rows) == 1
text = rows[0].read_text()
assert 'exit_code\\t124\\n' in text and 'partial\\ttrue\\n' in text
PY
''')

    def test_parallel_and_sequential_preserve_timeout(self):
        self.shell('''run_tool_with_anew() { [[ "$1" == slow ]] && return 124; return 0; }
for runner in run_tools_parallel run_tools_sequential; do
 rc=0; "$runner" 'slow::::' 'okay::::' || rc=$?
 [[ $rc -eq 124 ]]
done
''')

    def test_project_and_url_only_status(self):
        self.shell('''auth_seed_is_enabled() { return 1; }
get_profile_stages() { printf fixture; }
init_history_baseline() { :; }
copy_outputs_to_history() { :; }
show_results_summary() { :; }
execute_stage() { return 124; }
DIR_ONLY=false; DRY_RUN=false
rc=0; run_recon_project "$PROJECT_DIR" https://example.test test || rc=$?
[[ $rc -eq 124 ]]
rc=0; run_recon_url_only https://example.test test || rc=$?
[[ $rc -eq 124 ]]
trap - EXIT
''')


if __name__ == "__main__":
    unittest.main(verbosity=2)
