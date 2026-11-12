---
name: rust-serde
description: Use when writing or reviewing Rust types that derive serde Serialize/Deserialize - wire names, defaults, skipped fields, flatten, enum tagging, unknown keys, custom field codecs, validation on parse.
---

# Rust serde

Rules for the wire shape of Rust types. Dependencies: `serde` with the `derive` feature; a format crate (`serde_json`, `toml`, ...). Adding either to a project is a new dependency and must be said so.

## When to use

- A struct or enum derives `Serialize` / `Deserialize` and crosses a process boundary (HTTP body, config file, queue message, DB JSON column).
- You add a field to a type that already has stored or in-flight payloads.
- You choose how an enum looks on the wire.
- You validate input while parsing.

## Contents

1. [Rules](#rules)
2. [Decision tables](#decision-tables)
3. [Full rules](references/serde.md)

## Rules

Naming and compatibility:

- R-RSSD-RENAME-ALL: one container-level `#[serde(rename_all = "...")]` matching the external convention; field-level `rename` only for exceptions (keywords, one-offs). [serde-rename-all]
- R-RSSD-DEFAULT: new fields in a stored or in-flight payload get `#[serde(default)]` or `default = "fn"`; use the function form when `Default` is the wrong value; `Option<T>` already defaults to `None` and needs no attribute. [serde-default-compat]
- R-RSSD-SKIP-EMPTY: drop `None` / empty fields with `skip_serializing_if`, but never on a type that goes through a non-self-describing format (bincode, postcard): the reader expects every field and fails. [serde-skip-empty]

Shape:

- R-RSSD-FLATTEN: `#[serde(flatten)]` shares a field group across structs or captures extra keys in a map; it buffers input (slower) and is not for non-self-describing formats. [serde-flatten]
- R-RSSD-ENUM-TAG: choose the enum tagging on purpose and write it down; internally or adjacently tagged for public JSON, untagged only for a few structurally distinct variants. [serde-enum-representation]
- R-RSSD-DENY-UNKNOWN: `#[serde(deny_unknown_fields)]` on hand-written config files and strict request types, so a typo is an error; not together with `flatten`, and not where newer producers may add keys. [serde-deny-unknown-fields]

Conversion:

- R-RSSD-CUSTOM-WITH: when the wire type differs from the domain type, point serde at conversion functions (`with`, `serialize_with`, `deserialize_with`) instead of bending the field type; keep both directions symmetric. [serde-custom-with]
- R-RSSD-TRY-FROM: validate while parsing with `#[serde(try_from = "Raw")]` so an invalid value is never constructed; the `TryFrom` error is a `thiserror` enum. [serde-try-from-validate]

## Decision tables

| Situation | Use |
|---|---|
| External API uses camelCase / kebab-case | `rename_all` on the container |
| Field name is a Rust keyword | `rename` on that field |
| Field added after payloads exist | `default` (field level) |
| Whole struct is optional flags | container `#[derive(Default)]` + `#[serde(default)]` |
| Omit `None` / `[]` in JSON output | `skip_serializing_if` (JSON/TOML/YAML only) |
| Binary format (bincode, postcard) | no `skip_serializing_if`, no `flatten`, no internal/untagged enums |

| Enum wire format | Attribute | Tuple variants | Typical use |
|---|---|---|---|
| Externally tagged | none | yes | Rust to Rust |
| Internally tagged | `tag = "type"` | no (newtype around a struct/map is fine) | public JSON with discriminator |
| Adjacently tagged | `tag = "t", content = "c"` | yes | variants holding primitives or lists |
| Untagged | `untagged` | yes | a few clearly distinct shapes |

| Need | Use |
|---|---|
| One field with another wire type | `with = "module"` |
| Only one direction differs | `serialize_with` / `deserialize_with` (check the other direction round-trips) |
| Many types share the wire type | newtype with its own `Serialize` / `Deserialize` |
| Invalid values must not exist | `try_from` (+ `into` for output) |
