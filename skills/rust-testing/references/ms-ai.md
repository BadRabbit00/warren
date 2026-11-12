# Microsoft ai/ rules for tests

Source: Microsoft Rust Guidelines, `ai/M-TAUTOLOGICAL-TESTS`, MIT, © Microsoft Corporation.

## R-RST-NOT-TAUTOLOGICAL: tests do not assert ground truth [M-TAUTOLOGICAL-TESTS]

Why: a test that restates the expected value from the same definition the code uses, or mirrors the branches of the implementation, passes by construction. It adds noise to every later change and protects nothing. Generated tests do this often. If such a test exists only to kill a mutant, skip the mutant instead.

Check a property the value must satisfy, or an outcome the user can see.

Bad:
```rust
pub const CHECKPOINTS: [u32; 4] = [0, 90, 180, 270];

#[test]
fn checkpoints_are_correct() {
    assert_eq!(CHECKPOINTS, [0, 90, 180, 270]);
}
```
Why: the test is the constant copied; it can only fail when someone edits the constant, and then it is edited too.

Good:
```rust
use my_crate::CHECKPOINTS;

#[test]
fn checkpoints_are_evenly_spaced_and_increasing() {
    let steps: Vec<u32> = CHECKPOINTS.windows(2).map(|w| w[1] - w[0]).collect();
    assert!(steps.iter().all(|&s| s > 0), "checkpoints must increase");
    assert!(steps.windows(2).all(|w| w[0] == w[1]), "checkpoints must be evenly spaced");
}
```

Also tautological: asserting that a getter returns what the constructor was given, asserting `std` behaviour (`vec[100]` panics), and an expected value computed with the function under test.
