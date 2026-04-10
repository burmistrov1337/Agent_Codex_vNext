# Claude Gap And Target Spec

This document captures the current state of `Agent_Codex_vNext` against the Claude-style architecture patterns that we decided to use only as reference patterns, not as a copy target.

## Verdict Summary

### Done Enough

- modular repo layout with clear subsystems;
- baseline runtime contracts;
- hooks and safety skeleton;
- memory index, topic files, logs, and consolidation gates;
- first-wave command surface;
- headless CLI entrypoints;
- Telegram ingress MVP;
- marketplace vertical MVP;
- runtime-ready local scaffolding and operational hygiene.

### Needs Extension

- coordinator discipline and synthesis enforcement;
- background task model;
- tool registry and schema layer;
- memory extraction quality;
- deploy hardening and operational ergonomics;
- richer domain workflows.

### Redesign Required

- task bus and worker lifecycle;
- multi-agent spawn protocol;
- structured worker result envelope;
- separate synthesizer stage with explicit `continue vs spawn` logic.

### Explicitly Out Of Scope

- Bun/Ink/TypeScript runtime;
- decorative companion features;
- voice/computer-use layers;
- remote bridge complexity;
- giant slash-command surface;
- YOLO-style permission shortcuts.

## Block-By-Block Assessment

## 1. Runtime Core

### Current State

`vNext` already has task contracts, a task graph abstraction, an executor, and role-aware routing.

### Gap

It does not yet have a true task bus with leases, retries, lifecycle states, or durable background execution semantics.

### Decision

`redesign required`

### Target State

- introduce a real `TaskBus`;
- persist task lifecycle state;
- support retries, leases, and safe background pickup;
- separate interactive execution from background execution by contract, not by convention.

### Done When

- tasks can be queued, resumed, retried, and observed through one stable runtime API;
- scheduled and Telegram-driven runs use the same execution contract.

## 2. Coordinator And Synthesis

### Current State

The coordinator already reasons about roles and routes work, and critic/reviewer are available.

### Gap

Synthesis discipline is only partially enforced. Findings are not yet normalized through a dedicated synthesizer that turns outputs into precise next-step specs.

### Decision

`needs extension`

### Target State

- add a synthesizer stage owned by the coordinator;
- explicitly decide `continue existing branch` vs `spawn new worker`;
- require structured findings with evidence, gaps, artifacts, and follow-up actions.

### Done When

- worker outputs are always turned into a precise next-step spec;
- lazy handoff language is structurally prevented rather than merely discouraged.

## 3. Multi-Agent Runtime

### Current State

`vNext` is role-aware but still close to a single-runtime coordination model.

### Gap

There is no full worker spawn protocol, no peer/team runtime, and no durable shared worker envelope.

### Decision

`redesign required`

### Target State

- define spawned worker contracts;
- add shared scratchpad exchange rules;
- introduce structured worker result envelopes;
- keep synthesis owned by the coordinator.

### Done When

- parallel workers can be spawned safely without duplicating work;
- outputs compose into one deterministic final synthesis path.

## 4. Tools And Command Surface

### Current State

The first useful commands already exist: `doctor`, `memory`, `review`, `tasks`, `hooks`, `compact`, `marketplace-watch`, `study-digest`, `telegram-bot`.

### Gap

There is no richer tool registry with schemas, discovery, and explicit policy metadata.

### Decision

`needs extension`

### Target State

- add a tool registry with schemas and discovery metadata;
- keep the operator surface compact;
- only add second-wave commands that solve real user tasks.

### Done When

- tools are discoverable, validated, and policy-aware;
- commands remain small but clearly purposeful.

## 5. Hooks And Safety

### Current State

Protected paths, scratchpad allow-rules, and audit behavior are already present in the hooks pipeline.

### Gap

Risk classes are still shallow, explanations can be richer, and runtime-safe policies need more depth.

### Decision

`needs extension`

### Target State

- stronger risk classes per action family;
- clearer explanations before risky actions;
- stronger pre-reply quality gates;
- safer defaults for local automation and runtime scenarios.

### Done When

- risky operations are explainable, auditable, and consistently gated;
- Telegram and local runtime actions follow the same policy surface.

## 6. Memory And Consolidation

### Current State

`MEMORY.md`, topic files, daily logs, and consolidation gates already exist.

### Gap

Session-to-memory extraction is still lightweight, and topic freshness/drift handling remain simplistic.

### Decision

`needs extension`

### Target State

- stronger extraction from session results;
- better stale topic cleanup;
- conflict resolution for overlapping updates;
- absolute-date normalization during consolidation.

### Done When

- memory stays compact, current, and contradiction-aware over long-running use.

## 7. Background Tasks And Automation

### Current State

Marketplace watch, Telegram long polling, and `n8n` templates already exist in some form.

### Gap

There is no unified background-task contract that cleanly spans scheduler, bot, and domain automation.

### Decision

`needs extension`

### Target State

- one headless run envelope;
- one background task contract;
- predictable scheduled execution model;
- shared reporting and artifact contracts.

### Done When

- `n8n`, cron-like runs, and Telegram-triggered jobs produce the same class of run envelope and artifacts.

## 8. Marketplace Vertical

### Current State

Marketplace is the strongest domain vertical and already produces meaningful artifacts, including dashboards.

### Gap

It still needs a more complete production-ready vertical shape: deeper scenario coverage, stricter evidence handling, and stronger summary contracts.

### Decision

`needs extension`

### Target State

- richer scenario set;
- stricter evidence-first outputs;
- stronger summary, dashboard, and automation payload contracts;
- cleaner bridge to scheduled runs.

### Done When

- marketplace workflows can run both interactively and on schedule with consistent outputs and minimal ad-hoc glue.

## Priority Order For The Next Wave

### P1

- task bus;
- synthesizer stage;
- structured worker protocol.

### P2

- stronger memory extraction and consolidation;
- unified background runtime;
- deploy hardening.

### P3

- tool registry and schema layer;
- command surface second wave;
- richer marketplace vertical.

## Guiding Rule

`Agent_Codex_vNext` should not chase Claude-style complexity for its own sake. Every extension must make the system more useful, more predictable, or easier to operate for real work and study tasks.
