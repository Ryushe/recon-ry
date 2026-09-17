#!/usr/bin/env python3
"""Regression: param_recon.sh must preserve completed-phase output on interrupt.

recon-ry wraps param_recon.sh in ``timeout <N>``. On timeout the whole process
group gets SIGTERM, so any ``&& cat params_raw.txt > OUT`` appended after the
script never runs (the outer shell dies too). The old script also merged its
per-phase /tmp temps only at the very end and ran ``cleanup`` (rm -f every temp)
on ``EXIT INT TERM`` — so an interrupt deleted every temp *before* the merge and
the caller received an empty file despite hours of completed crawling.

The fix:
  * splits the trap so INT/TERM first merge whatever phase temps completed
    (truncation-safe) into params_raw.txt, then clean up, then re-raise;
  * writes the merged file to the caller-supplied ``--emit`` path from inside
    that trap, so a timeout-killed run still hands partial output back.

This test drives the real script fully offline with stub tools: waybackurls
completes, katana emits three complete lines plus one truncated (newline-less)
line and then hangs, and ``timeout`` fires mid-katana.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "param_recon.sh"

COMPLETE_LINES = [
    "https://example.com/k1?x=1",
    "https://example.com/k2?y=2",
    "https://example.com/k3?z=3",
    "https://example.com/wb?a=1",
    "https://example.com/wb?b=2",
]
TRUNCATED_LINE = "https://example.com/TRUNCATED-no-newline-partial"


@unittest.skipUnless(shutil.which("timeout"), "coreutils `timeout` required")
@unittest.skipUnless(shutil.which("bash"), "bash required")
class ParamReconInterruptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pr_interrupt_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.bindir = self.tmp / "bin"
        self.bindir.mkdir()

        # waybackurls: reads domains on stdin, emits canned URLs, exits fast.
        self._stub(
            "waybackurls",
            "cat >/dev/null\n"
            "printf 'https://example.com/wb?a=1\\nhttps://example.com/wb?b=2\\n'\n",
        )
        # katana: three complete lines, then a truncated line WITHOUT a newline,
        # then hang so `timeout` fires while this phase is mid-write.
        self._stub(
            "katana",
            "printf 'https://example.com/k1?x=1\\n"
            "https://example.com/k2?y=2\\n"
            "https://example.com/k3?z=3\\n'\n"
            f"printf '{TRUNCATED_LINE}'\n"  # no trailing newline
            "sleep 120\n",
        )

        (self.tmp / "alive.txt").write_text(
            "https://example.com/\nhttps://example.com/app\n"
        )

    def _stub(self, name: str, body: str) -> None:
        path = self.bindir / name
        path.write_text("#!/usr/bin/env bash\n" + body)
        path.chmod(0o755)

    def _run(self, args: list[str], timeout_s: int = 3) -> int:
        env = dict(os.environ)
        env["PATH"] = f"{self.bindir}{os.pathsep}{env['PATH']}"
        proc = subprocess.run(
            ["timeout", "--signal=TERM", str(timeout_s), "bash", "-c", *args],
            cwd=self.tmp,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.returncode

    def test_emit_receives_partial_on_sigterm(self) -> None:
        """Interrupted run: --emit file holds the completed-phase URLs."""
        outdir = self.tmp / ".param_recon_tmp"
        emit = self.tmp / "caller_output.txt"
        cmd = (
            f"rm -rf '{outdir}' && bash '{SCRIPT}' -i '{self.tmp / 'alive.txt'}' "
            f"-o '{outdir}' --emit '{emit}' --no-waymore --no-xnlinkfinder"
        )
        rc = self._run([cmd])
        self.assertEqual(rc, 124, "expected a timeout (124)")
        self.assertTrue(emit.exists(), "emit file must exist after interrupt")
        got = [ln for ln in emit.read_text().splitlines() if ln]
        # Completed phases (waybackurls + the flushed katana lines) survived.
        self.assertEqual(sorted(got), sorted(COMPLETE_LINES))
        # The truncated, newline-less final line must be dropped, not merged.
        self.assertNotIn(TRUNCATED_LINE, got)

    def test_no_tmp_garbage_left_after_interrupt(self) -> None:
        """The interrupt trap still cleans its /tmp phase temps."""
        before = set(Path("/tmp").glob("pr_*"))
        outdir = self.tmp / ".param_recon_tmp"
        emit = self.tmp / "caller_output.txt"
        cmd = (
            f"rm -rf '{outdir}' && bash '{SCRIPT}' -i '{self.tmp / 'alive.txt'}' "
            f"-o '{outdir}' --emit '{emit}' --no-waymore --no-xnlinkfinder"
        )
        self._run([cmd])
        after = set(Path("/tmp").glob("pr_*"))
        self.assertEqual(after - before, set(), "interrupt left /tmp phase temps behind")

    def test_happy_path_unchanged_and_clean(self) -> None:
        """Normal completion: full merge to --emit, no /tmp temps left."""
        # Fast katana stub that completes instead of hanging.
        self._stub(
            "katana",
            "printf 'https://example.com/k1?x=1\\n"
            "https://example.com/k2?y=2\\nhttps://example.com/k3?z=3\\n'\n",
        )
        before = set(Path("/tmp").glob("pr_*"))
        outdir = self.tmp / ".param_recon_tmp"
        emit = self.tmp / "caller_output.txt"
        cmd = (
            f"rm -rf '{outdir}' && bash '{SCRIPT}' -i '{self.tmp / 'alive.txt'}' "
            f"-o '{outdir}' --emit '{emit}' --no-waymore --no-xnlinkfinder"
        )
        rc = self._run([cmd], timeout_s=30)
        self.assertEqual(rc, 0, "happy path should exit 0")
        got = [ln for ln in emit.read_text().splitlines() if ln]
        self.assertEqual(sorted(got), sorted(COMPLETE_LINES))
        after = set(Path("/tmp").glob("pr_*"))
        self.assertEqual(after - before, set(), "happy path left /tmp temps behind")


if __name__ == "__main__":
    unittest.main()
