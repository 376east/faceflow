# FaceFlow releases

1. Run the **Release** workflow on the candidate branch to verify Windows Setup and the source ZIP. A manual run builds artifacts for review and cannot publish a release.
2. Select a commit reachable from `origin/master` with successful **CI** for its exact SHA on a `master` push. Choose a version higher than every published stable FaceFlow version. Keep technical releases outside the stable `vMAJOR.MINOR.PATCH` tag format.
3. Create and push an annotated `vMAJOR.MINOR.PATCH` tag at that commit. The workflow at the tagged commit runs the Setup install, launch, and uninstall tests and records SHA-256 digests for both packages and their checksum files. [Release workflow](../.github/workflows/release.yml)
4. The publication job queues behind other release promotions, stages the verified files on a draft, and checks GitHub's uploaded asset digests. It rechecks the live tag, master ancestry, exact push CI, and highest published stable version before making the draft public as Latest.

A failed promotion can leave a draft. Rerun the failed publication job to reuse the verified build. It resumes its own draft for the same tag object if the existing assets match. Keep the tag and any unrelated drafts intact while investigating a mismatch.

This procedure applies to commits that contain the current release workflow. GitHub loads the workflow from the tagged revision, so tags on commits from before the policy change use the workflow stored at those revisions.
