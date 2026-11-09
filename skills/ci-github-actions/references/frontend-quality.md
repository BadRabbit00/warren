# CI: frontend quality and accessibility (Lighthouse CI + axe)

"Readability" in the user's sense is accessibility plus Lighthouse scores. Install through npm as the project's devDependencies (pin versions in the lockfile): `@lhci/cli` (0.16.x in the research) and `@axe-core/cli` [source](https://raw.githubusercontent.com/GoogleChrome/lighthouse-ci/main/docs/getting-started.md). Do not `npm install -g` on the host.

## Lighthouse CI

- After the build: `npx lhci autorun` (the project's script).
- `lighthouserc.js`: `ci.assert.preset: 'lighthouse:recommended'` for gating, plus explicit assertions for the categories you want to hold (accessibility, performance, best practices).
- `ci.upload.target: 'temporary-public-storage'` uploads reports publicly, keeps them temporarily and gives no history; it does not fail the build. Gate with assertions; self-host an LHCI server for history. GitHub status checks use `LHCI_GITHUB_APP_TOKEN`.
- Action alternative `treosh/lighthouse-ci-action` (pin by SHA): inputs `urls`, `budgetPath`, `configPath`, `uploadArtifacts`, `temporaryPublicStorage`, `runs`, `serverBaseUrl`, `serverToken`, `artifactName` (default `lighthouse-results`) [source](https://raw.githubusercontent.com/treosh/lighthouse-ci-action/main/action.yml).

## axe CLI

```
npx axe <url> --exit                       # exit 1 on violations
npx axe <url> --exit --tags wcag2a         # limit to a rule set
```

Also `--rules`, `--disable`, `--chromedriver-path=<abs path>`; ChromeDriver via `npx browser-driver-manager install chrome` [source](https://raw.githubusercontent.com/dequelabs/axe-core-npm/develop/packages/cli/README.md). The ChromeDriver version must match the installed Chrome, or axe fails: pass a matching binary with `--chromedriver-path` or install the driver with browser-driver-manager.

axe finds only the issues automated rules can detect. It does not replace the `ui-verifier` check or manual keyboard and screen-reader review.

## Job shape

```yaml
a11y:
  runs-on: ubuntu-latest
  permissions: { contents: read }
  steps:
    - uses: actions/checkout@<full-sha> # vN
      with: { persist-credentials: false }
    - uses: actions/setup-node@<full-sha> # vN
      with: { node-version-file: .nvmrc, cache: npm }
    - run: npm ci
    - run: npm run build
    - run: npx lhci autorun
    - run: npm run a11y      # project script wrapping: start preview server, axe <url> --exit
```

Starting the preview server and waiting for readiness is project-specific; keep it in the project script, not in the workflow.
