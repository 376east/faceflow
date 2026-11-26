# FaceFlow releases

1. Run the **Release** workflow on the candidate branch to verify Windows Setup and the source ZIP. A manual run builds artifacts for review and cannot publish a release.
2. Verify that **CI** succeeded for the exact current `master` commit on a push event. Choose the next version after reviewing the changelog and the Windows artifacts.
3. Create and push an annotated `vMAJOR.MINOR.PATCH` tag at that commit. The tag workflow verifies the exact revision, builds both packages, runs the Setup install, launch, and uninstall smoke tests, and checks that the annotated tag and master still point to the verified commit before publishing. [Release workflow](../.github/workflows/release.yml)

Use the development workflow for packaging checks. The Windows Setup does not need an installed Python interpreter or a model download on the user's computer.
