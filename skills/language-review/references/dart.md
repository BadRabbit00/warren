# Flutter / Dart review

## Scope

You review Dart and Flutter problems in the diff: null-safety holes, lifecycle bugs, leaks, logic in widgets, and async mistakes. Visual checks are `ui-verifier`'s; Drift queries are `db-reviewer`'s; AC coverage is `code-reviewer`'s. The writer's rules are in `dart.md` (R-DART-*); you check them and go deeper.

## Tools

Run the project's tools on the changed files through `nix develop -c` (only tools the project has):
   - `dart analyze` (or `flutter analyze`) on the touched package;
   - `dart format --output=none --set-exit-if-changed <files>`;
   - `flutter test <affected tests>` only if the report you got has no numbers.

## Checklist

- **Null safety** (R-DART-NULL): `!` without a check; `late` fields read before init on some path; `as` casts on JSON without validation.
- **Lifecycle** (R-DART-CONTEXT, R-DART-DISPOSE): `BuildContext` or `setState` after `await` without a `mounted` check; controllers, subscriptions, timers not disposed; listeners added in `build`.
- **Layers** (R-DART-LAYERS): HTTP/DB calls in widgets; business rules in `build`; providers/blocs created inside `build`.
- **Async** (R-DART-ASYNC): futures neither awaited nor `unawaited`; errors in `Future.then` chains lost; streams without `onError`; `async` gaps in `initState` without guards.
- **Build performance** (R-DART-BUILD): heavy work or allocations in `build`; non-`const` widgets that could be; `ListView(children: [...])` for long lists; `setState` at the top of large trees.
- **Platform and storage** (R-DART-HTTP): tokens in `SharedPreferences`; HTTP without timeouts; `print` with personal data.

## Typical grades

Typical grades for this language:

| Finding | Usual grade |
|---|---|
| context or `setState` after an async gap without `mounted`; token in `SharedPreferences` | HIGH |
| undisposed subscription or controller on a screen users open often; network call from a widget | HIGH |
| missing `const`; `ListView(children:)` for a short list; `print` without personal data | MEDIUM / LOW |

## Must

- R-DARTR-TOOLS: report analyzer and format results with counts.
- R-DARTR-CASE: every HIGH names the user action that breaks ("leave the screen during save").

## Must not

- Edit files or install tools; judge visual design.

## Examples

### R-DARTR-SETSTATE — setState after the widget is gone

Bad:
```dart
Future<void> _load() async {
  final items = await repo.fetch();
  setState(() => _items = items);
}
```
Why: if the user leaves before the fetch ends, `setState` throws "called after dispose".

Good:
```dart
Future<void> _load() async {
  final items = await repo.fetch();
  if (!mounted) return;
  setState(() => _items = items);
}
```

### R-DARTR-TOKEN — secrets in plain storage

Bad:
```dart
final prefs = await SharedPreferences.getInstance();
await prefs.setString('refresh_token', token);
```
Why: plain-text storage, readable from backups and rooted devices.

Good:
```dart
const storage = FlutterSecureStorage();
await storage.write(key: 'refresh_token', value: token);
```

### R-DARTR-BUILD-WORK — work inside build

Bad:
```dart
@override
Widget build(BuildContext context) {
  final sorted = [...orders]..sort((a, b) => b.createdAt.compareTo(a.createdAt));
  return ListView(children: [for (final o in sorted) OrderTile(o)]);
}
```
Why: sorts and builds every tile on every rebuild; long lists jank on scroll.

Good:
```dart
@override
Widget build(BuildContext context) {
  final sorted = ref.watch(sortedOrdersProvider);      // computed once per change
  return ListView.builder(itemCount: sorted.length, itemBuilder: (_, i) => OrderTile(sorted[i]));
}
```

