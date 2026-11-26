from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import release_gate as gate


TAG = "v1.2.0"
TAG_OBJECT = "1" * 40
COMMIT = "2" * 40
MASTER = "3" * 40
REPO = "repos/376east/faceflow"
CI_RUN = {
    "head_branch": "master", "event": "push", "head_sha": COMMIT,
    "status": "completed", "conclusion": "success",
}


def release(tag, **fields):
    return {"tag_name": tag, "draft": False, "prerelease": False} | fields


class SourceGate(unittest.TestCase):
    def test_exact_annotated_ancestor_passes_as_master_advances(self):
        response = [
            {"object": {"type": "tag", "sha": TAG_OBJECT}},
            {"object": {"type": "commit", "sha": COMMIT}},
            {"object": {"sha": MASTER}},
            {"status": "ahead", "merge_base_commit": {"sha": COMMIT}},
            {"workflow_runs": [CI_RUN]},
        ]
        with patch.object(gate, "api", side_effect=response) as api:
            gate.require_source(REPO, TAG, TAG_OBJECT, COMMIT)
        api.assert_any_call(f"{REPO}/compare/{COMMIT}...{MASTER}?per_page=1")
        api.assert_any_call(
            f"{REPO}/actions/workflows/ci.yml/runs?branch=master&event=push&head_sha={COMMIT}&per_page=1"
        )

    def test_rejects_moved_tag_divergence_and_wrong_ci(self):
        good = [
            {"object": {"type": "tag", "sha": TAG_OBJECT}},
            {"object": {"type": "commit", "sha": COMMIT}},
            {"object": {"sha": MASTER}},
            {"status": "ahead", "merge_base_commit": {"sha": COMMIT}},
            {"workflow_runs": [CI_RUN]},
        ]
        cases = [
            (0, {"object": {"type": "tag", "sha": "4" * 40}}, "live tag"),
            (0, {"object": {"type": "commit", "sha": COMMIT}}, "live tag"),
            (1, {"object": {"type": "tag", "sha": COMMIT}}, "directly"),
            (3, {"status": "diverged", "merge_base_commit": {"sha": MASTER}}, "reachable"),
            (4, {"workflow_runs": []}, "exact release commit"),
            (4, {"workflow_runs": [CI_RUN | {"conclusion": "failure"}, CI_RUN]}, "exact release commit"),
            (4, {"workflow_runs": [CI_RUN | {"event": "pull_request"}]}, "exact release commit"),
            (4, {"workflow_runs": [CI_RUN | {"head_sha": MASTER}]}, "exact release commit"),
        ]
        for index, value, message in cases:
            with self.subTest(value=value):
                responses = good.copy()
                responses[index] = value
                with patch.object(gate, "api", side_effect=responses), self.assertRaisesRegex(ValueError, message):
                    gate.require_source(REPO, TAG, TAG_OBJECT, COMMIT)


class VersionGate(unittest.TestCase):
    def test_highest_published_regular_tag_wins_over_latest_pointer(self):
        releases = [
            release("v1.9.9", latest=True),
            release("v1.10.0"),
            release("delivery-check-v9.0.0"),
            release("v9.0.0", draft=True),
            release("v9.1.0", prerelease=True),
            release("v9.2.0-rc.1"),
        ]
        gate.require_newer("v1.10.1", releases)
        for tag in ("v1.9.10", "v1.10.0"):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "v1.10.0"):
                gate.require_newer(tag, releases)
        with self.assertRaisesRegex(ValueError, "stable"):
            gate.require_newer("v1.010.0", releases)


class Promotion(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        for name in (f"FaceFlow-{TAG}-Setup-x64.exe", f"FaceFlow-{TAG}-source.zip"):
            content = name.encode()
            (self.directory / name).write_bytes(content)
            (self.directory / f"{name}.sha256").write_text(f"{hashlib.sha256(content).hexdigest()}  {name}\n")
        self.digests = gate.verified_digests(self.directory, TAG)
        self.draft = release(TAG, id=1, draft=True, name=f"FaceFlow {TAG} for Windows",
                             body=f"Notes\n\n<!-- FaceFlow release workflow: {TAG_OBJECT} -->")
        self.assets = [
            {"name": name, "state": "uploaded", "digest": f"sha256:{digest}"}
            for name, digest in self.digests.items()
        ]

    def promote(self):
        gate.promote("376east/faceflow", TAG, TAG_OBJECT, COMMIT, self.directory, self.digests)

    def test_stages_entire_draft_rechecks_and_then_publishes(self):
        old = [release("v1.1.0")]
        calls = []

        def pages(endpoint):
            return next(listing if endpoint.endswith("/releases?per_page=100") else assets)

        listing = iter([old, old + [self.draft], old + [self.draft]])
        assets = iter([[], self.assets])

        def api(endpoint, *args):
            calls.append(("edit" if args else "get", endpoint))
            return release(TAG, html_url="https://github.com/376east/faceflow/releases/tag/" + TAG) if args else self.draft

        with (
            patch.object(gate, "pages", side_effect=pages),
            patch.object(gate, "require_source", side_effect=lambda *args: calls.append(("source", args))),
            patch.object(gate, "github", side_effect=lambda *args: calls.append(("cli", args))),
            patch.object(gate, "api", side_effect=api) as api_call,
            redirect_stdout(io.StringIO()) as console,
        ):
            self.promote()
        self.assertEqual([kind for kind, _ in calls], ["source", "cli", "cli", "get", "source", "edit"])
        self.assertIn("--draft", calls[1][1])
        self.assertEqual(calls[2][1][:2], ("release", "upload"))
        api_call.assert_called_with(f"{REPO}/releases/1", "--method", "PATCH",
                                    "-F", "draft=false", "-f", "make_latest=true")
        self.assertIn(f"/releases/tag/{TAG}", console.getvalue())

    def test_old_parallel_tag_leaves_its_draft_unpublished(self):
        with (
            patch.object(gate, "pages", side_effect=[
                [self.draft], self.assets, self.assets, [self.draft, release("v1.3.0")],
            ]),
            patch.object(gate, "require_source"),
            patch.object(gate, "github") as gh,
            patch.object(gate, "api") as api,
            self.assertRaisesRegex(ValueError, "v1.3.0"),
        ):
            self.promote()
        gh.assert_not_called()
        api.assert_not_called()

    def test_changed_draft_tag_and_wrong_hosted_digest_block_promotion(self):
        for case in ("draft-tag", "digest"):
            with self.subTest(case=case):
                draft = self.draft | {"tag_name": "v1.3.0"} if case == "draft-tag" else self.draft
                assets = self.assets if case == "draft-tag" else [self.assets[0] | {"digest": "sha256:wrong"}]
                with (
                    patch.object(gate, "pages", side_effect=[[self.draft], assets, assets, [self.draft]]),
                    patch.object(gate, "require_source"),
                    patch.object(gate, "github") as gh,
                    patch.object(gate, "api", return_value=draft) as api,
                    self.assertRaises(ValueError),
                ):
                    self.promote()
                gh.assert_not_called()
                self.assertEqual(api.call_count, int(case == "draft-tag"))

    def test_tampered_package_and_checksum_fail_against_independent_seal(self):
        path = self.directory / f"FaceFlow-{TAG}-Setup-x64.exe"
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum file"):
            gate.verified_digests(self.directory, TAG)
        (self.directory / f"{path.name}.sha256").write_text(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        )
        with patch.object(gate, "api") as api, self.assertRaisesRegex(ValueError, "verified package job"):
            self.promote()
        api.assert_not_called()
