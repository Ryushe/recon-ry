"""Offline Katana batching and two consumer paths, with a scanner stub."""
import importlib.util
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scope_filter", ROOT / "scripts/scope_filter.py")
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


class Batches(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name)
        self.bindir = self.p / "bin"
        self.bindir.mkdir()
        (self.p / "scope").write_text("*.example.test\nblocked.example.test\n")
        (self.p / "exclude").write_text("blocked.example.test\n*.private.example.test\n")
        self.env = dict(os.environ, RECON_RY_SCOPE_FILE=str(self.p / "scope"),
                        RECON_RY_OUT_SCOPE_FILE=str(self.p / "exclude"),
                        PATH=f"{self.bindir}:{os.environ['PATH']}")
        self.stub = self.bindir / "katana"
        self.stub.write_text("""#!/usr/bin/env python3
import os, pathlib, re, sys
args = sys.argv[1:]
assert args[args.index('-fs')+1] == 'fqdn'
assert '-dr' in args and '-cs' in args
inp = pathlib.Path(args[args.index('-list')+1])
out = pathlib.Path(args[args.index('-o')+1])
rx = re.compile(args[args.index('-cs')+1])
lines = inp.read_text().splitlines()
assert lines and all(rx.search(x) for x in lines), lines
assert all('blocked.' not in x and '.private.' not in x for x in lines)
with open(os.environ['KATANA_LOG'], 'a') as f:
    f.write(str(len(args[args.index('-cs')+1].encode())) + ':' + str(len(lines)) + '\\n')
with out.open('w') as f:
    f.write('\\n'.join(lines) + '\\n')
if os.environ.get('KATANA_TRUNCATE') and len(pathlib.Path(os.environ['KATANA_LOG']).read_text().splitlines()) == 2:
    with out.open('a') as f:
        f.write('https://h00000.example.test/trunc')
if os.environ.get('KATANA_SLOW') and len(pathlib.Path(os.environ['KATANA_LOG']).read_text().splitlines()) == 2:
    import time
    time.sleep(5)
if os.environ.get('KATANA_FAIL') and len(pathlib.Path(os.environ['KATANA_LOG']).read_text().splitlines()) == 2:
    sys.exit(7)
""")
        self.stub.chmod(0o755)
        self.env["KATANA_LOG"] = str(self.p / "calls")

    def seeds(self, n=20000):
        lines = [f"https://h{i:05d}.example.test/a" for i in range(n)]
        lines += ["https://blocked.example.test/", "https://x.private.example.test/",
                  "https://example.test/", "https://h00000.example.test.evil.test/"]
        (self.p / "input").write_text("\n".join(lines) + "\n")
        return lines[:n]

    def test_20k_batch_plan_exact_coverage_and_size(self):
        expected = self.seeds()
        s = scope.Scope(scope.load_rules(self.p / "scope"), scope.load_rules(self.p / "exclude"))
        count = scope.crawl_batches(s, self.p / "input", self.p / "batches")
        self.assertGreater(count, 1)
        self.assertLess(count, 30)
        seen = []
        for batch in sorted((self.p / "batches").glob("*.input")):
            rx = scope.crawl_regex(s, batch)
            self.assertLessEqual(len(shlex.quote(rx).encode()), 32768)
            lines = batch.read_text().splitlines()
            self.assertTrue(all(re.search(rx, line) for line in lines))
            self.assertIsNone(re.search(rx, "https://h00000.example.test.evil.test/"))
            seen.extend(lines)
        self.assertEqual(sorted(seen), sorted(expected))

    def test_exact_host_and_exclusion_deny_all(self):
        self.seeds(30)
        s = scope.Scope(scope.load_rules(self.p / "scope"), scope.load_rules(self.p / "exclude"),
                        "blocked.example.test")
        with self.assertRaisesRegex(ValueError, "no authorized crawler input"):
            scope.crawl_batches(s, self.p / "input", self.p / "batches")
        self.assertFalse(list((self.p / "batches").glob("*.input")))

    def test_shared_dispatch_success(self):
        expected = self.seeds(3000)
        script = f'''SCRIPT_DIR={shlex.quote(str(ROOT))}; source "$SCRIPT_DIR/src/scope.sh"
katana_run_batches 'katana -list {{{{INPUT}}}} -o {{{{OUTPUT}}}}' {shlex.quote(str(self.p / 'input'))} {shlex.quote(str(self.p / 'output'))}
'''
        run = subprocess.run(["bash", "-c", script], env=self.env,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(sorted((self.p / "output").read_text().splitlines()), sorted(expected))
        self.assertGreater(len((self.p / "calls").read_text().splitlines()), 1)

    def test_shared_dispatch_quotes_batch_paths_with_spaces(self):
        expected = self.seeds(3000)
        spaced = self.p / "scratch with spaces"
        spaced.mkdir()
        env = dict(self.env, TMPDIR=str(spaced))
        script = f'''SCRIPT_DIR={shlex.quote(str(ROOT))}; source "$SCRIPT_DIR/src/scope.sh"
katana_run_batches 'katana -list {{{{INPUT}}}} -o {{{{OUTPUT}}}}' {shlex.quote(str(self.p / 'input'))} {shlex.quote(str(self.p / 'output'))}
'''
        run = subprocess.run(["bash", "-c", script], env=env,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(sorted((self.p / "output").read_text().splitlines()), sorted(expected))

    def test_shared_dispatch_failure_and_partial(self):
        self.seeds(3000)
        self.env["KATANA_FAIL"] = "1"
        script = f'''SCRIPT_DIR={shlex.quote(str(ROOT))}; source "$SCRIPT_DIR/src/scope.sh"
katana_run_batches 'katana -list {{{{INPUT}}}} -o {{{{OUTPUT}}}}' {shlex.quote(str(self.p / 'input'))} {shlex.quote(str(self.p / 'output'))}
'''
        run = subprocess.run(["bash", "-c", script], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 7, run.stderr)
        self.assertIn("coverage", run.stderr.replace("remaining batches not crawled", "coverage"))
        self.assertGreater(len((self.p / "output").read_text().splitlines()), 0)
        self.assertLess(len((self.p / "output").read_text().splitlines()), 3000)
        self.assertEqual(len((self.p / "calls").read_text().splitlines()), 2)

    def test_aggregate_timeout_retains_prior_batches(self):
        self.seeds(3000)
        self.env["KATANA_SLOW"] = "1"
        script = f'''SCRIPT_DIR={shlex.quote(str(ROOT))}; source "$SCRIPT_DIR/src/scope.sh"
katana_run_batches 'katana -list {{{{INPUT}}}} -o {{{{OUTPUT}}}}' {shlex.quote(str(self.p / 'input'))} {shlex.quote(str(self.p / 'output'))}
'''
        run = subprocess.run(["timeout", "1", "bash", "-c", script], env=self.env,
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 124, run.stderr)
        got = (self.p / "output").read_text().splitlines()
        self.assertGreater(len(got), 0)
        self.assertLess(len(got), 3000)
        self.assertEqual(len((self.p / "calls").read_text().splitlines()), 2)

    def test_aggregate_timeout_drops_unterminated_active_line(self):
        self.seeds(3000)
        self.env.update(KATANA_SLOW="1", KATANA_TRUNCATE="1")
        script = f'''SCRIPT_DIR={shlex.quote(str(ROOT))}; source "$SCRIPT_DIR/src/scope.sh"
katana_run_batches 'katana -list {{{{INPUT}}}} -o {{{{OUTPUT}}}}' {shlex.quote(str(self.p / 'input'))} {shlex.quote(str(self.p / 'output'))}
'''
        run = subprocess.run(["timeout", "1", "bash", "-c", script], env=self.env,
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 124, run.stderr)
        got = (self.p / "output").read_text().splitlines()
        self.assertGreater(len(got), 0)
        self.assertNotIn("https://h00000.example.test/trunc", got)

    def test_param_recon_scoped_failure_is_nonzero(self):
        self.seeds(3000)
        self.env["KATANA_FAIL"] = "1"
        run = subprocess.run(["bash", str(ROOT / "scripts/param_recon.sh"),
                              "-i", str(self.p / "input"), "-o", str(self.p / "param"),
                              "--active-only", "--no-xnlinkfinder"], cwd=self.p,
                             env=self.env, capture_output=True, text=True, timeout=40)
        self.assertNotEqual(run.returncode, 0, run.stderr)
        self.assertIn("coverage incomplete", run.stderr)
        self.assertTrue((self.p / "param/params_raw.txt").exists())

    def test_param_scoped_timeout_emits_partial(self):
        self.seeds(3000)
        self.env["KATANA_SLOW"] = "1"
        emit = self.p / "emit"
        run = subprocess.run(["timeout", "3", "bash", str(ROOT / "scripts/param_recon.sh"),
                              "-i", str(self.p / "input"), "-o", str(self.p / "param"),
                              "--emit", str(emit), "--active-only", "--no-xnlinkfinder"],
                             cwd=self.p, env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 124, run.stderr)
        self.assertTrue(emit.exists(), run.stderr)
        self.assertGreater(len(emit.read_text().splitlines()), 0)

    def test_url_discovery_execute_tool_failure_receipt(self):
        self.seeds(3000)
        self.env["KATANA_FAIL"] = "1"
        script = f'''SCRIPT_DIR={shlex.quote(str(ROOT))}; PROJECT_DIR={shlex.quote(str(self.p))}; VERBOSE=0
source "$SCRIPT_DIR/src/logger.sh"; source "$SCRIPT_DIR/src/tools.sh"
is_tool_enabled() {{ return 0; }}
check_tool_exists() {{ return 0; }}
get_rate_limit() {{ printf 1; }}
get_install_info() {{ :; }}
get_payload_command() {{ :; }}
get_tool_info() {{ [[ "$2" == command ]] && printf 'katana -list {{{{INPUT}}}} -o {{{{OUTPUT}}}}'; }}
TOOL_TIMEOUT=15
execute_tool katana "$PROJECT_DIR/input" "$PROJECT_DIR/urls.txt" '' ''
'''
        run = subprocess.run(["bash", "-c", script], cwd=self.p, env=self.env,
                             capture_output=True, text=True, timeout=35)
        self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertTrue((self.p / "urls.txt").exists(), run.stdout + run.stderr)
        self.assertGreater(len((self.p / "urls.txt").read_text().splitlines()), 0)
        self.assertLess(len((self.p / "urls.txt").read_text().splitlines()), 3000)


if __name__ == "__main__":
    unittest.main()
