# profile-lint

Your GitHub profile README is a web page, but nobody tests it. `profile-lint`
runs seven deterministic checks over it and exits non-zero when something is
actually broken, so it can gate a pull request.

It exists because a real profile had three featured "systems" whose repositories
were private. Every visitor who clicked the strongest section of the page got a
404, and no test noticed.

## Quick start

```bash
python -m pip install -e .
profile-lint README.md --root .
```

Check the external links too (network, one HEAD request each):

```bash
profile-lint README.md --root . --links
```

Check a README you do not have on disk, without saving a temporary file:

```bash
gh api repos/someone/someone/readme -H "Accept: application/vnd.github.raw" | profile-lint -
```

Machine-readable output for CI:

```bash
profile-lint README.md --json
```

No dependencies beyond the Python standard library. Python 3.9 or newer.

## Rules

| Rule | Severity | What it catches |
|---|---|---|
| `empty` | error | the file has no content |
| `heading` | warning | no top-level `# ` heading |
| `alt-text` | error | an image without `alt`, in Markdown or HTML |
| `remote-image` | warning | an image fetched from another host at render time |
| `widget` | warning | a dependency on a badge or stats service |
| `claim` | error | marketing phrases that state a result nobody can check |
| `size` | warning | the README exceeds the byte budget (default 12,000) |
| `missing-path` | error | a relative link or image that does not exist in the repository |
| `scheme` | error | a `javascript:` or `data:` link |
| `dead-link` | error | an external link that answers 404/410 or another client error (only with `--links`) |
| `unverified-link` | warning | the host refuses `HEAD` (403, 405, 429, 5xx) so the status proves nothing |

`missing-path` is the rule that finds the case above without any network access:
a link to `./assets/hero.svg` only works if the file is where the README says it
is. `dead-link` needs `--links`, so the default run stays offline and fast.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | no errors (warnings do not fail the run) |
| 1 | at least one error |
| 2 | the file does not exist |

## Use it in CI

```yaml
- name: Lint the profile README
  run: |
    python -m pip install profile-lint
    profile-lint README.md --root . --links
```

## Limits, stated plainly

- The link check is a `HEAD` request. A host that rejects `HEAD` (LinkedIn does)
  can report a status that a browser never sees.
- `claim` matches a fixed list of phrases. It is not a fact checker; it cannot
  tell whether a number is true, only whether it is presented without evidence.
- Nothing here measures whether the software behind the links is good. A README
  that passes every rule can still belong to a bad project.

## Development

```bash
python -m unittest discover -s tests -v
python -m profilelint.cli README.md --root .
```

The second command runs the linter against this README, which is also what CI
does on every push. The rules live in [profilelint/rules.py](profilelint/rules.py);
the tests in [tests/test_rules.py](tests/test_rules.py) cover each one without
touching the network.

## License

MIT. See [LICENSE](LICENSE).
