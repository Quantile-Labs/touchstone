---
title: Systems
description: >-
  What a system is in a plan, how packs bind to one, and why Touchstone never
  talks to a model itself.
---

# Systems

A system is the thing being evaluated. A plan names them; a pack declares which ones it
needs; `validate` checks the two agree.
{ .lede }

```yaml
systems:
  chatbot:
    type: "llm_api"

packs:
  - id: "example_pack"
    systems:
      system_under_test: "chatbot"
```

`chatbot` is a name in this plan. `system_under_test` is the name the pack declared in its
manifest. The mapping between them is what lets one pack evaluate different systems, and
one plan run several packs against the same one.

## Touchstone does not talk to your model

This is the design decision that most distinguishes it from an evaluation framework, and
it is worth stating plainly: **there is no provider layer here.** No API clients, no
credential handling, no caching, no batching, no retry policy, no token accounting.

The pack talks to the system. Touchstone runs the pack, contains it, and does arithmetic on
what it emits.

The consequences are the point:

- **A pack for any system works without a change to the engine.** An HTTP API, a model
  behind a VPN, a batch scoring job, a phone tree. If it can be reached from a container
  and reduced to one row per item, it can be evaluated.
- **Credentials never reach Touchstone.** They are passed to the container, and the egress
  proxy that lets the container out [never terminates TLS](../running/containment.md).
- **The engine has nothing to be wrong about.** There is no request path to get subtly
  different between two runs.

What it costs you is real. Everything a framework gives you for free, including provider
retries, concurrency and response caching, is yours to write inside the pack. That is the
trade, and
if you are exploring rather than publishing it is the wrong one. Use
[Inspect](https://inspect.aisi.org.uk/) for that.

## Fields

| Field | Type | Notes |
|---|---|---|
| `type` | string | Required. Free-form. `validate` matches it against the type the pack declared. |
| `params` | map | Optional. Passed to the pack as `--systems-params` JSON. |

## Types

The engine does not know what types exist. `llm_api` appears in the examples because the
example pack declares it needs one. A pack that declares `type: "credit_scorer"` and a plan
that supplies one work identically.

A pack may accept more than one:

```yaml title="manifest.yaml"
input_systems:
  - name: "system_under_test"
    type: ["llm_api", "llm_local"]
    required: true
```

## How a pack receives them

`run` passes the bound systems to the container as a JSON string:

```text
--systems-params '{"system_under_test": {"type": "llm_api", "params": {...}}}'
```

The pack parses that and does whatever it does. See [Writing a
pack](../extending/writing-a-pack.md).

## Required and optional

```yaml
input_systems:
  - name: "system_under_test"
    type: "llm_api"
    required: true
  - name: "reference"
    type: "llm_api"
    required: false
```

`validate` fails a plan that does not supply a required system. An optional one that is
absent is simply absent, and the pack decides what that means.
