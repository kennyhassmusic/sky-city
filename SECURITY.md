# Security

## Get the game only from the official page

The only official download is **https://kornontheken.itch.io/sky-city**. Official Mac builds are:

- **signed** with the Developer ID of *Kenny Hass Music LLC* (team **F89LBX9V56**), and
- **notarized** by Apple, so macOS opens them without warnings.

You can check a download yourself in Terminal:

```bash
codesign -dv --verbose=2 "Sky City.app" 2>&1 | grep -E "Authority|TeamIdentifier"
spctl -a -vv "Sky City.app"
```

You should see `Developer ID Application: Kenny Hass Music LLC (F89LBX9V56)` and `source=Notarized Developer ID`. If you don't, don't run it, and tell us where you got it. Each release's GitHub notes also list the SHA-256 checksum of the download.

## Report a vulnerability

Please **don't** open a public issue for security problems. Use GitHub's **"Report a vulnerability"** button on the repository's Security tab, which reaches the maintainers privately. We'll reply as soon as we can, and credit you if you'd like.

Examples worth reporting: anything that runs code when the project or a map is opened, a malicious asset or script in the repository, a compromised build, or leaked credentials.

## How we protect the project

Open projects can be attacked from the inside: someone builds trust over time, then slips in something harmful. The 2024 *xz-utils* backdoor is the best-known example; it hid in build scripts and test files. Our defences:

- **Trust is earned slowly** and is never all-or-nothing (see [GOVERNANCE.md](GOVERNANCE.md)). Nobody but Kenny can publish a release or holds the signing keys.
- **Sensitive files need Kenny's review**, whoever proposes the change: build and packaging scripts, CI workflows, project and engine config, plugins, licences, and anything the editor runs by itself (see `.github/CODEOWNERS`).
- **No opaque files in code areas.** Binaries, archives, compiled libraries and executables are rejected automatically outside the art folders (the `pr-guard` check). Test data must be readable text.
- **Nothing runs on its own.** Editor start-up scripts (`init_unreal.py`, `Content/Python/`), editor-utility assets that run at startup, and new third-party tools or dependencies need a maintainer's explicit approval.
- **Release builds are made on a known machine**, from a signed tag, never from an unreviewed branch. CI never handles signing keys and never runs pull-request code with secrets.
- **Accounts:** everyone with write access uses two-factor authentication and signed commits. Access is reviewed regularly, and unused access is removed.
