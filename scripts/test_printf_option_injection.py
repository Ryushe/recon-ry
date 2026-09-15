#!/usr/bin/env python3
"""Regression: a printf format that starts with '-' is parsed as options.

`printf -v VAR '-cs %q -dr' "$X"` fails with "printf: -c: invalid option" and
leaves VAR empty. In param_recon.sh that silently dropped katana's crawl scope,
so the crawler ran with neither -cs nor -dr.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# `printf [-v NAME] FORMAT ...` — capture the first quoted token after any -v NAME.
PRINTF_CALL = re.compile(
    r"""printf\s+(?:-v\s+\S+\s+)?(?:--\s+)?(?P<quote>['"])(?P<fmt>.*?)(?P=quote)"""
)


def shell_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.sh"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [ROOT / line for line in out.stdout.split() if line]


class PrintfFormatTests(unittest.TestCase):
    def test_no_printf_format_begins_with_a_dash(self):
        offenders = []
        for path in shell_files():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "printf" not in line or "--" in line.split("printf", 1)[1][:12]:
                    continue
                match = PRINTF_CALL.search(line)
                if match and match.group("fmt").startswith("-"):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
        self.assertEqual(
            offenders,
            [],
            "printf format starts with '-' and will be parsed as options; "
            "build it from '%s' or pass '--' first:\n" + "\n".join(offenders),
        )

    def test_dash_leading_format_actually_breaks(self):
        """Pin the underlying behaviour so the rule above is not cargo cult."""
        broken = subprocess.run(
            ["bash", "-c", 'printf -v X "-cs %q -dr" "R"; printf "%s" "$X"'],
            capture_output=True,
            text=True,
        )
        self.assertEqual(broken.stdout, "")
        self.assertIn("invalid option", broken.stderr)

    def test_supported_forms_produce_the_expected_arguments(self):
        for script in (
            'printf -v X "%s %q %s" "-cs" "R" "-dr"; printf "%s" "$X"',
            'printf -v X -- "-cs %q -dr" "R"; printf "%s" "$X"',
        ):
            with self.subTest(script=script):
                result = subprocess.run(
                    ["bash", "-c", script], capture_output=True, text=True, check=True
                )
                self.assertEqual(result.stdout, "-cs R -dr")

    def test_param_recon_builds_a_nonempty_crawl_scope(self):
        """The fixed call site must yield both -cs and -dr for a real scope."""
        source = (ROOT / "scripts" / "param_recon.sh").read_text(encoding="utf-8")
        self.assertIn("KATANA_SCOPE_ARGS", source)
        line = next(
            l for l in source.splitlines() if "printf -v KATANA_SCOPE_ARGS" in l
        ).strip()
        result = subprocess.run(
            ["bash", "-c", f'CRAWL_SCOPE="REGEX"; {line}; printf "%s" "$KATANA_SCOPE_ARGS"'],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout, "-cs REGEX -dr", result.stderr)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
