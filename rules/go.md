---
paths:
  - "**/*.go"
  - "**/go.mod"
---

# Go

## Scope

Go services (Gin, GORM, slog). Layers, DB, and tests have their own rules; this is the language part. `language-reviewer` checks it in depth.

Checks: `go test -race` (touched packages); `go vet ./...`; `golangci-lint run`.

## Rules

- R-GO-ERRORS: every returned error is checked. Wrap with context: `fmt.Errorf("load order %s: %w", id, err)`; compare with `errors.Is` / `errors.As`. Domain errors are sentinel values or types in `internal/domain`. No `panic` in handlers or library code.
- R-GO-CTX: `ctx context.Context` is the first parameter of anything that does I/O; the request context flows down to the DB and HTTP calls. No `context.Background()` inside a request path.
- R-GO-GOROUTINES: every goroutine has an owner, a way to stop (ctx), and its errors collected (`errgroup.WithContext` + `SetLimit`). No goroutine per item without a limit.
- R-GO-SHARED: maps and slices shared between goroutines are guarded (`sync.Mutex`) or owned by one goroutine; tests run with `-race`.
- R-GO-INTERFACES: accept interfaces, return structs. A small interface is declared by its consumer, next to it; no interface "for the future".
- R-GO-RESOURCES: `defer resp.Body.Close()` after the error check; no `defer` inside a loop (wrap the body in a function).
- R-GO-HTTP: outgoing calls use an `http.Client` with `Timeout` set, created once; servers set `ReadHeaderTimeout`. Never `http.DefaultClient`.
- R-GO-LOGGING: `log/slog` with key-value attributes; no `fmt.Println` / `log.Printf` in services.
- R-GO-NAMES: short lower-case package names, no `util` / `common`; files `<entity>_<layer>.go`; exported names have doc comments.

## Examples

### R-GO-ERRORS — never drop an error

Bad:
```go
order, _ := repo.Get(ctx, id)
json.NewEncoder(w).Encode(order)
```
Why: a DB failure becomes a `null` body with status 200.

Good:
```go
order, err := repo.Get(ctx, id)
if errors.Is(err, domain.ErrOrderNotFound) {
    return nil, err
}
if err != nil {
    return nil, fmt.Errorf("get order %s: %w", id, err)
}
```

### R-GO-RESOURCES — defer in a loop

Bad:
```go
for _, p := range paths {
    f, err := os.Open(p)
    if err != nil { return err }
    defer f.Close()          // closes only when the function returns
    process(f)
}
```
Why: with many files the process runs out of descriptors.

Good:
```go
for _, p := range paths {
    if err := processFile(p); err != nil {
        return err
    }
}

func processFile(p string) error {
    f, err := os.Open(p)
    if err != nil { return err }
    defer f.Close()
    return process(f)
}
```
