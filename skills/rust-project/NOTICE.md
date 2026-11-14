# Notice

This skill adapts rules from two MIT-licensed sources.

| Source | Commit | Licence | Copyright |
|---|---|---|---|
| https://github.com/leonardomso/rust-skills (rules with the prefixes `proj-` and `lint-`) | `fd2a861a` | MIT | © 2025 Leonardo Maldonado |
| https://github.com/microsoft/rust-guidelines (`universal/M-STATIC-VERIFICATION`, `universal/M-LINT-OVERRIDE-EXPECT`, `project/M-CARGO-WORKSPACE`, `project/M-CRATES-IN-WORKSPACE`, `project/M-LATEST-EDITION`, `project/M-MSRV`, and `ai/M-SINGLE-ITEM-PATH` as a reason for dropping the prelude rule) | `9585e288` | MIT | © Microsoft Corporation |

Adapted: rules selected, merged and rewritten.
Rules were checked against stable Rust, edition 2024 (Rust 1.99, clippy 0.1.99), and against this repository's `rules/rust.md`.
Several examples were corrected; the corrections are not part of the upstream text.
