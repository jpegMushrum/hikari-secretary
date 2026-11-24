"""Exercise the Linux VPS rollout without running services or touching a Git remote."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


DEPLOY = Path(__file__).resolve().parent


@unittest.skipUnless(os.name == "posix", "The Actions runner uses Linux")
class SantaWorkflowTests(unittest.TestCase):
    def dispatch(self, action, season_id):
        with tempfile.TemporaryDirectory() as directory:
            ssh = Path(directory, "ssh")
            ssh.write_text('#!/bin/bash\nprintf "%s" "${!#}"\n')
            ssh.chmod(0o755)
            return subprocess.run(
                ["bash", str(DEPLOY / "production-ssh.sh")], capture_output=True, text=True,
                env={**os.environ, "PATH": os.pathsep.join((directory, os.environ["PATH"])),
                     "RUNNER_TEMP": directory, "DEPLOY_PATH": "/opt/hikari", "DEPLOY_PORT": "22",
                     "DEPLOY_HOST": "localhost", "DEPLOY_USER": "test", "DEPLOY_SSH_KEY": "test",
                     "DEPLOY_KNOWN_HOSTS": "test", "PRODUCTION_ACTION": action, "SANTA_SEASON_ID": season_id},
            )

    def test_operator_can_start_or_close_a_specific_season(self):
        for action, season_id, suffix in (("start-santa", "", "santa-start"), ("close-santa", "12", "santa-close 12")):
            with self.subTest(action=action):
                result = self.dispatch(action, season_id)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.endswith("/app/api " + suffix), result.stdout)

    def test_close_requires_valid_explicit_id_before_ssh(self):
        for value in ("", "0", "-1", "1 2", "9223372036854775808"):
            with self.subTest(value=value):
                result = self.dispatch("close-santa", value)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


@unittest.skipUnless(os.name == "posix", "The deployment target runs Linux")
class ProductionReleaseTests(unittest.TestCase):
    def rollout(self, *, fail_migration=False, reject_commit=False):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / ".env").write_text("POSTGRES_DB=test\n")
            (work / "deploy").mkdir()
            shutil.copy(DEPLOY / "pin_images.py", work / "deploy")
            git = work / "git"
            git.write_text("""#!/bin/sh
case "$1 $2" in
    "rev-parse --git-path") echo deploy.lock ;;
    "branch --show-current") echo main ;;
    "merge-base --is-ancestor") exit "$REJECT_COMMIT" ;;
esac
""")
            docker = work / "docker"
            docker.write_text("""#!/bin/sh
echo "$*" >> commands
case "$*" in
    *--exit-code-from*) exit "$FAIL_MIGRATION" ;;
esac
""")
            git.chmod(0o755)
            docker.chmod(0o755)
            refs = [f"ghcr.io/example/hikari-secretary-{component}@sha256:{'e' * 64}"
                    for component in ("backend", "bot", "miniapp")]
            result = subprocess.run(
                ["bash", "-s", "--", "a" * 40, *refs], input=(DEPLOY / "production-release.sh").read_text(),
                cwd=work, capture_output=True, text=True,
                env={**os.environ, "PATH": os.pathsep.join((directory, os.environ["PATH"])),
                     "REJECT_COMMIT": str(int(reject_commit)), "FAIL_MIGRATION": "23" if fail_migration else "0"},
            )
            commands = work / "commands"
            return result, commands.read_text() if commands.exists() else "", (work / ".env").read_text()

    def test_migration_failure_stops_before_application_rollout(self):
        result, commands, config = self.rollout(fail_migration=True)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIn("BOT_IMAGE=ghcr.io/", config)
        self.assertIn("pull backend bot miniapp", commands)
        self.assertNotIn("bot miniapp", commands.split("--exit-code-from")[-1])

    def test_rejected_revision_leaves_images_and_running_stack_untouched(self):
        result, commands, config = self.rollout(reject_commit=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(commands, "")
        self.assertEqual(config, "POSTGRES_DB=test\n")

    def test_success_waits_for_the_applications(self):
        result, commands, _ = self.rollout()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--wait", commands.splitlines()[-1])
        self.assertTrue(commands.rstrip().endswith("bot miniapp"))
