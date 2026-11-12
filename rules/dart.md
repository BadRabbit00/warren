---
paths:
  - "**/*.dart"
  - "**/pubspec.yaml"
---

# Dart and Flutter

## Scope

Flutter apps and Dart packages. Visual rules are in `design.md`; on-device data in `db.md` (Drift). This is the language and framework part. `language-reviewer` checks it in depth.

Checks: `dart analyze` (or `flutter analyze`); `dart format --output=none --set-exit-if-changed`; `flutter test`.

## Rules

- R-DART-NULL: sound null safety; no `!` without a check right above; `late` only when initialisation is guaranteed before first read.
- R-DART-CONTEXT: never use a `BuildContext` after an `await` without `if (!context.mounted) return;` (or `if (!mounted) return;` in a `State`).
- R-DART-DISPOSE: every controller, `FocusNode`, `AnimationController`, `StreamSubscription`, and `Timer` created by a widget is disposed or cancelled in `dispose()`.
- R-DART-LAYERS: widgets render and forward events; logic lives in the project's state layer (Riverpod notifiers or Bloc), data access in repositories. No HTTP or DB calls from widgets.
- R-DART-ASYNC: every `Future` is awaited or wrapped in `unawaited(...)` on purpose, with errors handled; streams are listened to with `onError`.
- R-DART-BUILD: `build()` has no side effects and no expensive work; `const` constructors where possible; long lists use `ListView.builder`.
- R-DART-LOGGING: no `print`; use the project's logger. Secrets never; personal data only at DEBUG, masked at INFO and above (skill `logging`).
- R-DART-HTTP: one HTTP client (`dio`/`http`) configured with timeouts and interceptors in the data layer; tokens in `flutter_secure_storage`, never in `SharedPreferences`.

## Examples

### R-DART-CONTEXT — context across an async gap

Bad:
```dart
Future<void> _save() async {
  await ref.read(orderRepoProvider).save(order);
  Navigator.of(context).pop();          // the widget may be gone
}
```
Why: if the user left the screen during the save, this throws or navigates the wrong route.

Good:
```dart
Future<void> _save() async {
  await ref.read(orderRepoProvider).save(order);
  if (!mounted) return;
  Navigator.of(context).pop();
}
```

### R-DART-DISPOSE — release what you create

Bad:
```dart
class _SearchState extends State<Search> {
  final _controller = TextEditingController();
  late final StreamSubscription<String> _sub = widget.queries.listen(_onQuery);
  // no dispose()
}
```
Why: the listener keeps firing after the screen is closed and leaks the state object.

Good:
```dart
@override
void dispose() {
  _sub.cancel();
  _controller.dispose();
  super.dispose();
}
```
