# Security policy

Touchstone produces evidence that other people are asked to trust, so a defect that
lets a bundle say something false is a security defect here even where it would be a
correctness bug elsewhere. Report those the same way you would report a container
escape.

## Supported versions

| Version | Supported |
|---|---|
| 0.3.x | yes |
| earlier | no |

There is one supported version at a time and it is the latest release on PyPI. The
project is pre-alpha and there are no backports. A fix arrives in the next release,
and `docs/project/status.md` records what an already sealed bundle is known to have
got wrong, since a bundle cannot be corrected after the fact.

## Reporting a vulnerability

**Use GitHub's private vulnerability reporting.** Go to the
[Security tab](https://github.com/Quantile-Labs/touchstone/security) of this
repository and choose *Report a vulnerability*. The report stays private to the
maintainers until a fix is published.

If that is unavailable to you, email **kayode@quantilelabs.com** with `touchstone` in
the subject.

Please do not open a public issue, and please do not disclose publicly before a fix
is released.

**What to include.** The version, the command you ran, a plan or a pack that
reproduces it, and what you expected against what happened. A pack that demonstrates
the problem is worth more than a description of one.

**What to expect.** An acknowledgement within five working days and an assessment
within fifteen. If the report is accepted you will be told the release it is going
into, and you will be credited in the release notes unless you ask otherwise.

## What is in scope

Three boundaries carry weight here, and a way past any of them is a vulnerability.

**Containment.** A pack runs on a docker network created `--internal`, which has no
route off the host, and a squid sidecar attached to both that network and the bridge
is the only way out. It allows `CONNECT` to the hosts the pack declared in its
manifest and denies everything else, and it never terminates TLS. Every container
runs `--read-only`, with `--cap-drop ALL`, `--security-opt no-new-privileges`, as the
calling user, and under a memory, CPU and process cap with `--memory-swap` pinned to
the memory figure. **A pack reaching a host it did not declare, escaping the
container, or reading the host beyond its two mounts is in scope**, including through
the allowlist itself: a declared host is checked against a hostname pattern before it
is written into a proxy config, and a way to smuggle a squid directive through that
check is the shape of bug this section exists for.

**The evidence path.** `bundle` hashes every file and `verify` re-hashes them
offline. A way to change a file that a sealed bundle covers while `verify` still
passes is in scope, and so is a way to make `bundle` seal a run that never finished.

**The arithmetic that becomes a claim.** An interval that does not cover what it says
it covers is a defect of this kind. Two have shipped, and both are recorded in the
status page rather than quietly fixed.

## What is out of scope

- **What a pack itself does.** A pack is somebody else's code and Touchstone's job is
  to contain it, not to vet it. A malicious pack that stays inside its declared
  egress, its resource cap and its mounts is behaving as designed.
- **The system under test.** A weakness in a model or an endpoint an evaluation
  points at belongs to whoever runs it.
- **Anything requiring an attacker who already controls the machine running
  Touchstone.** The output directory is host-owned and writable by the caller by
  design.
- **The documentation site.** It is a static GitHub Pages build with no server side.

## Known gaps that are not news

Both are recorded in the design documents and neither is treated as a report.

- **Secrets are not redacted from captured output.** `02-DESIGN.md` describes
  redaction by pattern and by known value and nothing in `src/` implements it. What
  limits exposure is that `--capture-stdout` is off by default, so a pack that logs a
  credential only writes it into the bundle when someone asks for its stdout. Do not
  turn that flag on for a bundle you intend to hand over until this is built.
- **A pinned image is not a pinned system.** `freeze` pins the pack image to a
  digest. There is no digest for somebody else's endpoint, which can move under the
  same model name between two runs of one frozen plan.

## Verifying a release

Releases are published to PyPI through
[trusted publishing](https://docs.pypi.org/trusted-publishers/), so no token is stored
anywhere and the publishing identity is this repository rather than a person. The
artefacts carry PyPI attestations that tie a release on the index back to the tag it
was built from.
