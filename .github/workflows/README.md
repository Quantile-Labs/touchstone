`ci.yml` runs three jobs.

- `test`: lint, format check, unit tests.
- `commit-messages`: every commit in a pull request is checked against
  `scripts/check_commit_msg.py`. See CONTRIBUTING.md.
- `offline-install`: builds a wheel, vendors its dependencies, then installs and runs
  with no package index. Touchstone has to work in an environment with no egress, so
  that claim is tested on every push rather than asserted in the README.
