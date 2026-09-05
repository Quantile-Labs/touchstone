---
title: Contracts
description: >-
  Generated API reference for the pydantic models that define every file format
  in a bundle.
---

# Contracts

Every file in a bundle is one of these models. They are the format: what `bundle` writes,
what `verify` reads, and what a third-party reader would implement against.
{ .lede }

All are `pydantic` models with `extra="forbid"`, so an unknown key raises rather than being
quietly dropped.

## Plan

::: touchstone.contracts.plan

## Manifest

::: touchstone.contracts.manifest

## Lock

::: touchstone.contracts.lock

## Item records

::: touchstone.contracts.item

## Estimates

::: touchstone.contracts.estimates

## Score cards

::: touchstone.contracts.scorecard

## Command output

::: touchstone.contracts.diagnostics

## Conformance

::: touchstone.contracts.report

## Audit responses

::: touchstone.contracts.audit

## Environment

::: touchstone.contracts.environment

## Bundle manifest

::: touchstone.contracts.bundle
