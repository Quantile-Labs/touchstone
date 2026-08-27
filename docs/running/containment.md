---
title: Containment
description: >-
  How a pack gets exactly the hosts it declared and nothing else, and why the
  proxy that lets it out never sees a credential.
---

# Containment

A pack that asks for no network gets none. A pack that lists hosts gets those and nothing
else.
{ .lede }

The enforcement is structural. The container runs on a Docker network created
`--internal`, which has no route off the host, and a small proxy attached to both that
network and the bridge is the only door.

## Declaring

```yaml title="manifest.yaml"
network:
  egress: ["api.openai.com"]
```

`network.egress` is a declaration a security reviewer can read. `freeze` copies it into
`plan.lock.json`, so the review reads the frozen plan rather than pulling an image.

**Empty means the pack reaches nothing**, and that is enforced: the container runs with no
network at all.

## Containment does not depend on your pack

The container is told about the proxy through `HTTPS_PROXY` and the usual spellings. That is
a **courtesy rather than the control**.

A pack that ignores those variables is on a network with nowhere to go. The internal
network is what makes the answer irrelevant.

```text
┌─────────────────────────────┐
│  internal network           │      ┌────────┐
│  (no route off the host)    │      │ bridge │
│                             │      └───┬────┘
│   ┌──────┐      ┌─────────┐ │          │
│   │ pack │─────▶│  squid  │─┼──────────┘
│   └──────┘      └─────────┘ │   CONNECT to declared hosts only
└─────────────────────────────┘
```

## The proxy never terminates TLS

The proxy reads the hostname off the `CONNECT` line and the bytes stay opaque. It is never
trusted with your API keys.

**That is the constraint the design is built around rather than a limitation of it.** A
proxy that decrypted traffic to filter it would be a component that sees every credential
the pack uses, sitting in the middle of an evidence pipeline. There is no version of that
which is worth the extra filtering.

## What may be declared

Hostnames, and nothing else.

| Not allowed | Why |
|---|---|
| a scheme (`https://…`) | not a hostname |
| a port | not a hostname |
| a path | not a hostname |
| a wildcard | not a hostname |
| a bare IP address | `dstdomain` matches names rather than addresses, so an address would be accepted and then match nothing |

A host that is not a hostname is refused before anything starts. A denial with no
explanation is worse than a refusal with one.

`dstdomain example.com` matches that host and **not its subdomains**, so a pack that needs
a subdomain declares the subdomain.

## What the bundle records

`environment.json` carries `egress_enforced: true`, and every request the pack made,
allowed or denied, is written to `<run_id>.egress.log` beside its records.

!!! warning "A denial in there is a finding rather than an error"

    It says the pack tried to reach a host it never declared. The run completed; the log
    is where that shows up.

## `--allow-unenforced-egress`

```console
$ touchstone run ./run-004 -o ./run-004 --allow-unenforced-egress
```

A downgrade of something the backend can now do. It runs the pack on the ordinary bridge
network with the whole internet available, and records `egress_enforced: false` so a reader
knows the pack was not contained.

Use it to develop against a real API. **It is not a way to produce evidence for anyone.**

If any unit in a run was unenforced, the whole run's `egress_enforced` is `false`. A claim
that a pack was contained is not available for that bundle.
