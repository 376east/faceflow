"""Verify exact GitHub release inputs and promote a fully staged draft."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SHA = re.compile(r"[0-9a-f]{40}")


def version(tag):
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"Expected a stable vMAJOR.MINOR.PATCH tag, got {tag!r}")
    return tuple(map(int, match.groups()))


def github(*args):
    return subprocess.check_output(["gh", *args], encoding="utf-8").strip()


def api(endpoint, *args):
    return json.loads(github("api", endpoint, *args))


def pages(endpoint):
    return [item for page in api(endpoint, "--paginate", "--slurp") for item in page]


def require_source(repo, tag, tag_object, commit):
    version(tag)
    if not SHA.fullmatch(tag_object) or not SHA.fullmatch(commit):
        raise ValueError("Missing or invalid exact release SHA")
    ref = api(f"{repo}/git/ref/tags/{tag}")["object"]
    if ref["type"] != "tag" or ref["sha"] != tag_object:
        raise ValueError("The live tag is not the verified annotated tag")
    target = api(f"{repo}/git/tags/{tag_object}")["object"]
    if target["type"] != "commit" or target["sha"] != commit:
        raise ValueError("The annotated tag does not point directly to the verified commit")
    master = api(f"{repo}/git/ref/heads/master")["object"]["sha"]
    if not SHA.fullmatch(master):
        raise ValueError("GitHub did not return a valid live master SHA")
    compare = api(f"{repo}/compare/{commit}...{master}?per_page=1")
    if compare["status"] not in ("ahead", "identical") or compare["merge_base_commit"]["sha"] != commit:
        raise ValueError("The verified commit is not reachable from live master")
    runs = api(
        f"{repo}/actions/workflows/ci.yml/runs?branch=master&event=push&head_sha={commit}&per_page=1"
    )["workflow_runs"]
    if not runs or any(runs[0].get(key) != value for key, value in {
        "head_branch": "master", "event": "push", "head_sha": commit,
        "status": "completed", "conclusion": "success",
    }.items()):
        raise ValueError("The latest master push CI for the exact release commit must have succeeded")


def require_newer(tag, releases):
    candidate = version(tag)
    published = [
        (version(item["tag_name"]), item["tag_name"])
        for item in releases
        if not item["draft"] and not item["prerelease"] and TAG.fullmatch(item["tag_name"])
    ]
    if published and candidate <= max(published)[0]:
        raise ValueError(f"{tag} must be newer than the highest published stable tag {max(published)[1]}")


def verified_digests(directory, tag):
    version(tag)
    archives = (f"FaceFlow-{tag}-Setup-x64.exe", f"FaceFlow-{tag}-source.zip")
    names = {name for filename in archives for name in (filename, f"{filename}.sha256")}
    if {path.name for path in directory.iterdir()} != names:
        raise ValueError("Release artifact must contain the two packages and their checksum files")
    digests = {}
    for name in sorted(names):
        with (directory / name).open("rb") as stream:
            digests[name] = hashlib.file_digest(stream, "sha256").hexdigest()
    for archive in archives:
        if (directory / f"{archive}.sha256").read_text(encoding="ascii").split() != [digests[archive], archive]:
            raise ValueError(f"The checksum file does not match {archive}")
    return digests


def verify_assets(repo, release_id, digests):
    found = set()
    for asset in pages(f"{repo}/releases/{release_id}/assets?per_page=100"):
        name = asset["name"]
        if (name in found or name not in digests or asset["state"] != "uploaded"
                or asset.get("digest") != f"sha256:{digests[name]}"):
            raise ValueError(f"The draft contains an unexpected or unverified asset {name!r}")
        found.add(name)
    return found


def require_draft(release, tag, title, stamp):
    if (release["tag_name"] != tag or not release["draft"] or release["prerelease"]
            or release["name"] != title or not (release["body"] or "").rstrip().endswith(stamp)):
        raise ValueError("The matching release is not a draft created by this workflow for the verified tag")


def promote(repository, tag, tag_object, commit, directory, sealed):
    repo = f"repos/{repository}"
    digests = verified_digests(directory, tag)
    if digests != sealed:
        raise ValueError("The downloaded artifact differs from the verified package job")
    require_source(repo, tag, tag_object, commit)
    release_list = f"{repo}/releases?per_page=100"
    releases = pages(release_list)
    require_newer(tag, releases)
    drafts = [release for release in releases if release["tag_name"] == tag]
    stamp = f"<!-- FaceFlow release workflow: {tag_object} -->"
    title = f"FaceFlow {tag} for Windows"
    if not drafts:
        setup = f"FaceFlow-{tag}-Setup-x64.exe"
        notes = (
            f"Run [FaceFlow Setup for Windows x64](https://github.com/{repository}/releases/download/{tag}/{setup}) "
            "and open FaceFlow from the Start menu. Setup includes the runtime and recognition models. "
            "For the source ZIP, follow INSTALL.md. "
            f"[Инструкция на русском](https://github.com/{repository}/blob/{tag}/README.ru.md).\n\n{stamp}"
        )
        github("release", "create", tag, "--repo", repository, "--verify-tag", "--draft",
               "--latest=false", "--title", title, "--notes", notes)
        drafts = [release for release in pages(release_list) if release["tag_name"] == tag]
    if len(drafts) != 1:
        raise ValueError("GitHub did not return exactly one candidate draft")
    require_draft(drafts[0], tag, title, stamp)
    release_id = drafts[0]["id"]
    missing = digests.keys() - verify_assets(repo, release_id, digests)
    if missing:
        github("release", "upload", tag, "--repo", repository,
               *(str(directory / name) for name in sorted(missing)))
    if verify_assets(repo, release_id, digests) != digests.keys():
        raise ValueError("The complete verified asset set is not present in the draft")
    require_newer(tag, pages(release_list))
    require_draft(api(f"{repo}/releases/{release_id}"), tag, title, stamp)
    require_source(repo, tag, tag_object, commit)
    release = api(f"{repo}/releases/{release_id}", "--method", "PATCH",
                  "-F", "draft=false", "-f", "make_latest=true")
    if release["draft"] or release["prerelease"] or release["tag_name"] != tag:
        raise ValueError("GitHub did not confirm publication of the expected release")
    print(release["html_url"])


def output(name, value):
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as file:
        print(f"{name}={value}", file=file)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("preflight", "seal", "publish"))
    parser.add_argument("--assets", type=Path)
    args = parser.parse_args()
    tag = os.environ["GITHUB_REF_NAME"]
    repository = os.environ["GITHUB_REPOSITORY"]
    if args.step == "preflight":
        version(tag)

        def revision(ref):
            return subprocess.check_output(["git", "rev-parse", "--verify", ref], encoding="ascii").strip()

        tag_object = revision(f"refs/tags/{tag}")
        commit = revision("HEAD")
        if (revision(f"{tag_object}^{{commit}}") != commit
                or os.environ["GITHUB_SHA"] not in (tag_object, commit)
                or os.environ["TAG_PUSH_AFTER"] not in (tag_object, commit)):
            raise ValueError("The build checkout and annotated object do not match the tag push")
        require_source(f"repos/{repository}", tag, tag_object, commit)
        output("tag-object", tag_object)
        output("commit", commit)
    elif args.step == "seal":
        output("digests", json.dumps(verified_digests(args.assets, tag), separators=(",", ":")))
    else:
        promote(repository, tag, os.environ["TAG_OBJECT"], os.environ["TAG_COMMIT"],
                args.assets, json.loads(os.environ["SEALED_DIGESTS"]))


if __name__ == "__main__":
    main()
