---
description: Review .nix changes with the nix-reviewer agent — merging bugs, types, hashes and fetchers, purity/IFD, secrets in the store, systemd hardening, home.file on mutable files, platform guards, lint. MUST follow any .nix edit.
argument-hint: "[paths | diff range]"
---

# /nix-review

Invoke **nix-reviewer** on `$ARGUMENTS` or `git diff -- '*.nix'`. If the change also touched other languages, run `language-reviewer` separately with an explicit folder scope (e.g. on `backend/**/*.py`); the Nix reviewer handles only `.nix` and generated files.

Expect findings by severity with file:line, lint output, and a ship/fix-first verdict. Fix CRITICAL and HIGH before continuing; list MEDIUM/LOW for the user.
