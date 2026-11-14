# serde rules in full

Adapted from leonardomso/rust-skills `serde-*` (see ../NOTICE.md). Examples use stable Rust, edition 2024.

## R-RSSD-RENAME-ALL — match the external naming

Rust fields are `snake_case`; JSON APIs often use `camelCase`. Per-field `rename` on every field is noisy and easy to get wrong. A container-level `rename_all` applies to serialization and deserialization; for enums it renames variants. A field-level `rename` wins over it.

Bad:
```rust
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct UserProfile {
    #[serde(rename = "firstName")]
    first_name: String,
    #[serde(rename = "emailAddress")]
    email_address: String,
    #[serde(rename = "isActive")]
    is_active: bool,
}
```

Good:
```rust
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct UserProfile {
    first_name: String,
    email_address: String,
    is_active: bool,
    // exception: a Rust keyword
    #[serde(rename = "type")]
    user_type: String,
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
enum Status {
    Active,
    PendingVerification,
}
```

Values: `lowercase`, `UPPERCASE`, `PascalCase`, `camelCase`, `snake_case`, `SCREAMING_SNAKE_CASE`, `kebab-case`, `SCREAMING-KEBAB-CASE`.

## R-RSSD-DEFAULT — new fields must not break old payloads

Without a default, a missing key is a "missing field" error. When a field is added to a type whose payloads are already stored or in flight, old payloads stop parsing.

- Field level `#[serde(default)]` uses the field type's `Default`.
- `#[serde(default = "path")]` calls `fn() -> T`; use it when `Default` is the wrong value (timeout 30, not 0).
- Container level `#[serde(default)]` needs `Default` on the struct; every missing field then comes from the struct's `Default` value (so a hand-written `Default` supplies non-zero values).
- `Option<T>` fields are already `None` when the key is missing; `#[serde(default)]` on them is redundant.
- `default` affects only deserialization.

Bad:
```rust
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct Config {
    host: String,
    port: u16,
    timeout_secs: u64, // added later: old configs fail with "missing field"
    retries: u32,      // same
}
```

Good:
```rust
use serde::{Deserialize, Serialize};

fn default_retries() -> u32 {
    3
}

#[derive(Serialize, Deserialize)]
struct Config {
    host: String,
    port: u16,
    #[serde(default)]
    timeout_secs: u64,
    #[serde(default = "default_retries")]
    retries: u32,
    tls_cert_path: Option<String>, // missing key is already None
}

// all-optional flags: one attribute on the container
#[derive(Serialize, Deserialize, Default)]
#[serde(default)]
struct FeatureFlags {
    enable_caching: bool,
    enable_metrics: bool,
}
```

Caveat: container-level `default` makes every field optional, which hides typos in field names. Prefer field level when only some fields are later additions, or pair with `deny_unknown_fields`.

## R-RSSD-SKIP-EMPTY — omit empty values, but only for self-describing formats

`None` becomes `null` and empty collections `[]`; that bloats payloads and confuses clients that tell a missing key from `null`. `#[serde(skip_serializing_if = "path")]` takes any `fn(&T) -> bool` (`Option::is_none`, `Vec::is_empty`, `String::is_empty`, a custom predicate) and drops the field from the output.

**Warning: do not use `skip_serializing_if` on a type serialized with a non-self-describing format (bincode, postcard, and similar).** Those formats write fields by position with no names; a skipped field shifts the layout, and the reader fails or misreads. The same holds for `flatten`, internally tagged and untagged enums. If one type serves both JSON and a binary format, use separate wire types.

Related attributes: `#[serde(skip)]` removes a field in both directions and needs `Default` for deserialization; `skip_serializing` / `skip_deserializing` skip one direction only. Pair `skip_serializing_if` with `default` (or use `Option`) so the missing key also reads back.

Bad:
```rust
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct ApiResponse {
    id: u64,
    description: Option<String>, // {"id":1,"description":null,"tags":[]}
    tags: Vec<String>,
}
```

Good (JSON only):
```rust
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct ApiResponse {
    id: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    description: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    tags: Vec<String>, // {"id":1}
    #[serde(skip)]
    cache_key: Option<String>, // never on the wire
}
```

## R-RSSD-FLATTEN — share fields, collect extra keys

`#[serde(flatten)]` merges a nested struct's fields into the parent's wire form, so repeated groups (pagination, audit stamps) are defined once. A flattened map collects every key no other field claims.

Bad:
```rust
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct UserList {
    users: Vec<String>,
    page: u32,
    per_page: u32,
    total: u64,
}

#[derive(Serialize, Deserialize)]
struct PostList {
    posts: Vec<String>,
    page: u32,
    per_page: u32,
    total: u64,
}
```

Good:
```rust
use std::collections::HashMap;

use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct Pagination {
    page: u32,
    per_page: u32,
    total: u64,
}

#[derive(Serialize, Deserialize)]
struct UserList {
    users: Vec<String>,
    #[serde(flatten)]
    pagination: Pagination, // {"users":[..],"page":1,"per_page":20,"total":100}
}

#[derive(Serialize, Deserialize)]
struct Flexible {
    name: String,
    #[serde(flatten)]
    extra: HashMap<String, serde_json::Value>, // catch-all
}
```

Caveats:
- Incompatible with `deny_unknown_fields` on the same struct.
- Deserialization buffers the input, so it is slower; avoid it on hot paths.
- Not for non-self-describing formats such as bincode.
- Several flattened fields are fine as long as their key sets do not overlap.

## R-RSSD-ENUM-TAG — pick the enum representation deliberately

The default (externally tagged) wraps each variant in an object keyed by the variant name, `{"Circle":{"radius":5.0}}`. Public APIs usually expect a discriminator field. The wrong choice shows up as parse failures or lost round-trips, so choose and document it.

| Strategy | Attribute | Wire form | Tuple variants |
|---|---|---|---|
| Externally tagged | none | `{"Circle":{"radius":5}}` | yes |
| Internally tagged | `tag = "type"` | `{"type":"Circle","radius":5}` | no |
| Adjacently tagged | `tag = "t", content = "c"` | `{"t":"Circle","c":{"radius":5}}` | yes |
| Untagged | `untagged` | `{"radius":5}` | yes |

Bad:
```rust
use serde::{Deserialize, Serialize};

// externally tagged by accident: {"Circle":{"radius":5.0}}
// while the API contract is {"type":"circle","radius":5.0}
#[derive(Serialize, Deserialize)]
enum Shape {
    Circle { radius: f64 },
    Rectangle { width: f64, height: f64 },
}
```

Good:
```rust
use serde::{Deserialize, Serialize};

// {"type":"circle","radius":5.0}
#[derive(Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum Shape {
    Circle { radius: f64 },
    Rectangle { width: f64, height: f64 },
}

// variants holding primitives need adjacent tagging: {"t":"count","c":3}
#[derive(Serialize, Deserialize)]
#[serde(tag = "t", content = "c", rename_all = "snake_case")]
enum Measure {
    Count(u32),
    Area { width: f64, height: f64 },
}

// a few clearly distinct shapes only
#[derive(Serialize, Deserialize)]
#[serde(untagged)]
enum Number {
    Integer(i64),
    Float(f64),
    Text(String),
}
```

Caveats:
- Untagged tries variants in declaration order, is slower, can pick the wrong variant and gives generic errors. Reserve it for small, structurally distinct sets.
- Internally tagged cannot hold tuple variants or newtypes around primitives or sequences; a newtype around a struct or map works. Use adjacent tagging for the rest.
- Internally tagged, adjacently tagged and untagged enums need a self-describing format; bincode does not support the first and last of these.

## R-RSSD-DENY-UNKNOWN — turn typos into errors

By default serde drops keys that match no field, so `"timout_secs"` is accepted and `timeout_secs` stays unset. `#[serde(deny_unknown_fields)]` makes unknown keys an error naming the key.

Use it for: hand-written config files, strict request types, any contract where a typo must surface. Skip it when producers may be newer than the consumer and add keys (rolling deploys, third-party webhooks); there, collect extras with a flattened map instead. It cannot be combined with `flatten` on the same struct; split the struct, or parse into `serde_json::Value` first.

Bad:
```rust
use serde::Deserialize;

#[derive(Deserialize)]
struct ServerConfig {
    host: String,
    port: u16,
    #[serde(default)]
    timeout_secs: u64,
}

fn parse(json: &str) -> Result<ServerConfig, serde_json::Error> {
    // {"host":"h","port":1,"timout_secs":30} parses; the typo is dropped
    // and timeout_secs silently stays 0
    serde_json::from_str(json)
}
```

Good:
```rust
use serde::Deserialize;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ServerConfig {
    host: String,
    port: u16,
    #[serde(default)]
    timeout_secs: u64,
}

fn parse(json: &str) -> Result<ServerConfig, serde_json::Error> {
    serde_json::from_str(json) // "timout_secs" -> error: unknown field `timout_secs`
}
```

## R-RSSD-CUSTOM-WITH — convert at the field, keep the domain type

When the wire format needs another representation (a `Duration` as seconds, a timestamp as text), changing the field type to a primitive leaks the wire format into the domain. Point serde at conversion functions instead.

- `with = "module"`: the module has `pub fn serialize<S: Serializer>(&T, S) -> Result<S::Ok, S::Error>` and `pub fn deserialize<'de, D: Deserializer<'de>>(D) -> Result<T, D::Error>`.
- `serialize_with = "path"` / `deserialize_with = "path"`: one direction only. The other direction stays derived, so check that the type still round-trips; usually give both or neither.
- Existing modules: chrono ships `chrono::serde::ts_seconds` and similar, usable with `with`. `serde_with` is a separate crate and would be a new dependency.
- Many types sharing a wire form: a newtype with its own impls is cleaner than repeating the attribute.
- Watch for lossy conversions: seconds drop sub-second precision.

Bad:
```rust
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct Task {
    name: String,
    timeout_secs: u64, // every caller converts to and from Duration
}
```

Good:
```rust
use std::time::Duration;

use serde::{Deserialize, Deserializer, Serialize, Serializer};

mod duration_secs {
    use super::*;

    pub fn serialize<S: Serializer>(value: &Duration, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_u64(value.as_secs())
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(deserializer: D) -> Result<Duration, D::Error> {
        u64::deserialize(deserializer).map(Duration::from_secs)
    }
}

#[derive(Serialize, Deserialize)]
struct Task {
    name: String,
    // wire: {"name":"..","timeout":30}; Rust: Duration
    #[serde(with = "duration_secs", rename = "timeout")]
    timeout: Duration,
}
```

## R-RSSD-TRY-FROM — never construct an invalid value

Validating after deserialization lets an invalid value exist, and callers forget the check. `#[serde(try_from = "Raw")]` deserializes `Raw`, then calls `TryFrom<Raw>`; an `Err` becomes a deserialization error. `#[serde(into = "Raw")]` serializes through `From<T> for Raw` and requires `T: Clone`. The attributes replace the derived field-by-field impl. The `TryFrom` error must implement `Display`; make it a `thiserror` enum (`thiserror` is an existing project dependency for errors). The same `TryFrom` serves CLI parsing and forms.

Bad:
```rust
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct Email(String); // "notanemail" deserializes fine

fn handle(json: &str) -> Result<(), serde_json::Error> {
    let email: Email = serde_json::from_str(json)?;
    // the caller must remember to validate; nothing enforces it
    let _ = email;
    Ok(())
}
```

Good:
```rust
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Error)]
#[error("invalid email address: {0}")]
struct InvalidEmail(String);

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
struct Email(String);

impl TryFrom<String> for Email {
    type Error = InvalidEmail;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        match value.split_once('@') {
            Some((local, domain)) if !local.is_empty() && !domain.is_empty() => Ok(Self(value)),
            _ => Err(InvalidEmail(value)),
        }
    }
}

impl From<Email> for String {
    fn from(value: Email) -> Self {
        value.0
    }
}

// serde_json::from_str::<Email>("\"notanemail\"") is an Err; no invalid Email exists.
```
