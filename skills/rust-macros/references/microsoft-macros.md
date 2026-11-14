# Macro rules (from Microsoft `macros/`)

Rules not already merged into `macro.md` (R-RSM-LAST-RESORT, R-RSM-PRIVATE-HELPERS, R-RSM-PROC-CRATES contain M-MACRO-LAST-RESORT, M-MACRO-HELPERS, M-PROC-IMPL).

### R-RSM-EXAMPLE-OVER-PROC — `macro_rules!` before a proc macro

Proc macros are more powerful, but their expansion is hard to inspect and they cost compile time. When a macro by example can do the job, use it.

Bad:
```rust
// attribute proc macro just to declare a newtype
#[make_new_id]
struct MyId;
```
Why: needs proc-macro machinery and a separate crate for something a declarative macro does.

Good:
```rust
macro_rules! make_new_id {
    ($name:ident) => {
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
        struct $name(u64);
    };
}

make_new_id!(MyId);
```

### R-RSM-DONT-LIE — macros do not misrepresent items

A macro can rewrite tokens arbitrarily; it must not. It does not turn a struct into an enum, add or remove function parameters, change `async`-ness, or otherwise separate what is written from what happens. A reader (or an agent) must be able to predict a call from the source text.

Bad:
```rust
// the attribute adds a parameter and makes the function async
#[magic_transform]
fn foo() {}

async fn caller(token: Token) {
    foo(token).await;
}
```
Why: the signature in the source is not the signature in use.

Good:
```rust
// the attribute only adds behaviour; the signature stays as written
#[traced]
fn foo() {}

fn caller() {
    foo();
}
```

### R-RSM-NO-IMPLIED-ITEMS — no invisible extra items

A macro must not define extra named types next to the user's item (`struct ExtraType` returned from a generated method). They can clash with user types or with other expansions of the same macro, break naming conventions, and are invisible in the source, so they are forgotten when re-exporting. Generate only what the user wrote, or items the user names explicitly in the macro input.

One tolerated exception: a type with the same name as a function (different namespace), as in route-handler or FFI macros; the generated type is not for public use.

Bad:
```rust
#[my_macro]
struct UserType;

// expands to
struct UserType;
struct ExtraType;                 // invisible, may clash, not re-exported
impl UserType { fn foo() -> ExtraType { ExtraType } }
```
Why: `ExtraType` can collide with another item in the module and nobody sees it in the source.

Good:
```rust
// the user names the generated item
my_macro!(UserType, UserTypeHandle);

// expands to
struct UserType;
struct UserTypeHandle;
impl UserType { fn foo() -> UserTypeHandle { UserTypeHandle } }
```
