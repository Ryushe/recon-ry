#!/usr/bin/env python3
"""Offline regressions: fractional rate limits and url_discovery corpus promotion.

Defect 1 (observed 2026-11-04, linktree-mbb-og): a project rate_limit.conf
default of 0.5 req/s was substituted verbatim into `-rl {{RATE_LIMIT}}`, and
the ProjectDiscovery tools parse -rl as an int, so httpx/katana/nuclei all
died with `invalid value "0.5" for flag -rl: parse error` (exit 2) before
sending a single request. alive_check then failed, which cascaded into
http_fingerprinting/param_discovery/url_ranking being skipped.

Defect 2 (same run): url_discovery merges its harvest into .tmp_run/urls.txt
and .tmp_run is wiped at the start of the next run. When url_ranking skipped,
1,399,847 harvested URLs were stranded and the final project urls.txt still
held only the seed lines while the run printed "Recon completed!".
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import test_defensive_boundaries as boundaries  # noqa: E402


class RateLimitTests(boundaries.ShellTests):
    def httpx_command(self):
        return "httpx -list {{INPUT}} -silent -mc 200,301 -rl {{RATE_LIMIT}} -o {{OUTPUT}}"

    def test_httpx_fractional_rate_becomes_per_minute_flag(self):
        out = self.shell(
            'command="$(apply_rate_limit_substitution httpx 0.5 "%s")"\n'
            '[[ "$command" == *"-rlm 30 "* ]]\n'
            '[[ "$command" != *"-rl 0.5"* ]]\n'
            '[[ "$command" != *"-rl 1 "* ]]\n'
            'printf "%%s" "$command"' % self.httpx_command()
        )
        self.assertIn("-rlm 30 ", out)

    def test_httpx_quarter_rate_rounds_to_fifteen_per_minute(self):
        out = self.shell(
            'command="$(apply_rate_limit_substitution httpx 0.25 "%s")"\n'
            'printf "%%s" "$command"' % self.httpx_command()
        )
        self.assertIn("-rlm 15 ", out)

    def test_integer_rates_pass_through_untouched(self):
        out = self.shell(
            'command="$(apply_rate_limit_substitution httpx 2 "%s")"\n'
            '[[ "$command" == *"-rl 2 "* ]]\n'
            '[[ "$command" != *"-rlm"* ]]\n'
            'printf "%%s" "$command"' % self.httpx_command()
        )
        self.assertIn("-rl 2 ", out)

    def test_non_httpx_fractional_rates_clamp_to_one(self):
        for tool, template in (
            ("katana", "katana -list {{INPUT}} -d 3 -silent -rl {{RATE_LIMIT}} -o {{OUTPUT}}"),
            ("nuclei", "nuclei -list {{INPUT}} -silent -rl {{RATE_LIMIT}} -o {{OUTPUT}}"),
            ("subfinder", "subfinder -dL {{ROOTS_FILE}} -all -silent -rl {{RATE_LIMIT}} -o {{OUTPUT}}"),
            ("ffuf", "ffuf -u FUZZ -w {{INPUT}} -rate {{RATE_LIMIT}} -o {{OUTPUT}}"),
        ):
            out = self.shell(
                'command="$(apply_rate_limit_substitution %s 0.5 "%s")"\n'
                'printf "CMD:%%s\\n" "$command"' % (tool, template)
            )
            cmd_line = next(line for line in out.splitlines() if line.startswith("CMD:"))
            self.assertNotIn("0.5", cmd_line, tool)
            self.assertNotIn("{{RATE_LIMIT}}", cmd_line, tool)
            self.assertIn(" 1 ", cmd_line, tool)

    def test_zero_and_empty_rates_behave_as_before(self):
        out = self.shell(
            'c0="$(apply_rate_limit_substitution katana 0 "%s")"\n'
            'ce="$(apply_rate_limit_substitution katana "" "%s")"\n'
            '[[ "$c0" == *" 0 "* ]]\n'
            '[[ "$ce" == *"-rl  -o"* ]]\n'
            'printf "ok"' % (
                "katana -list {{INPUT}} -silent -rl {{RATE_LIMIT}} -o {{OUTPUT}}",
                "katana -list {{INPUT}} -silent -rl {{RATE_LIMIT}} -o {{OUTPUT}}",
            )
        )
        self.assertIn("ok", out)


class CorpusPromotionTests(boundaries.ShellTests):
    def shell_fs(self, body):
        """Like shell(), but with output.sh sourced for the promotion helper."""
        return self.shell('source "$SCRIPT_DIR/src/output.sh"\n' + body)

    def test_corpus_promotes_deduped_into_project_urls(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "project"
            temp = project / ".tmp_run"
            temp.mkdir(parents=True)
            (project / "urls.txt").write_text("https://example.test/a\nhttps://example.test/b\n")
            (temp / "urls.txt").write_text(
                "https://example.test/b\nhttps://example.test/c\nhttps://example.test/d\n"
            )
            out = self.shell_fs(
                'promote_temp_urls_to_project "%s" "%s"\n'
                'sort "%s/urls.txt"' % (project, temp, project)
            )
            lines = [line for line in out.splitlines() if line.startswith("https://")]
            self.assertEqual(
                lines,
                [
                    "https://example.test/a",
                    "https://example.test/b",
                    "https://example.test/c",
                    "https://example.test/d",
                ],
            )

    def test_promotion_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "project"
            temp = project / ".tmp_run"
            temp.mkdir(parents=True)
            (project / "urls.txt").write_text("https://example.test/a\n")
            (temp / "urls.txt").write_text("https://example.test/a\nhttps://example.test/c\n")
            body = (
                'promote_temp_urls_to_project "%s" "%s"\n'
                'promote_temp_urls_to_project "%s" "%s"\n'
                'sort "%s/urls.txt"' % (project, temp, project, temp, project)
            )
            lines = [
                line
                for line in self.shell_fs(body).splitlines()
                if line.startswith("https://")
            ]
            self.assertEqual(lines, ["https://example.test/a", "https://example.test/c"])

    def test_empty_or_missing_corpus_is_a_noop(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "project"
            temp = project / ".tmp_run"
            temp.mkdir(parents=True)
            (project / "urls.txt").write_text("https://example.test/a\n")
            self.shell_fs(
                'promote_temp_urls_to_project "%s" "%s"\n'
                '[[ $(wc -l < "%s/urls.txt") -eq 1 ]]' % (project, temp, project)
            )


class SyntaxTests(unittest.TestCase):
    def test_shell_modules_parse(self):
        for module in ("src/tools.sh", "src/stages.sh", "src/output.sh"):
            result = subprocess.run(
                ["bash", "-n", str(ROOT / module)], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, f"{module}: {result.stderr}")

    def test_stage_configs_are_valid_yaml_with_expected_dependency(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml unavailable")
        for config in ("config/general.yaml", "config/defaults/general.yaml"):
            data = yaml.safe_load((ROOT / config).read_text())
            self.assertEqual(
                data["stages"]["url_ranking"]["depends_on"],
                ["alive_check"],
                config,
            )


if __name__ == "__main__":
    unittest.main()
