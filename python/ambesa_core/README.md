# ambesa-core

Vendor-neutral primitives that `ambesa-bench` builds on: typed data shapes, the `LLMProvider` Protocol with an Anthropic implementation, the eval grading layer, and the public tool surface.

This package does not contain Ambesa's hosted production agent — it lives behind the cloud product. What's here is the contract layer the public benchmark grades against.

## What's here

- `types.py` — `Incident`, `AgentRun`, `Diagnosis`, `FixProposal`, `FailureClass`, `Prompt`, `TokenUsage`, the related enums + nested shapes.
- `llm.py` — `LLMProvider` Protocol + `AnthropicProvider` implementation + `CachePolicy` + `ModelId`. The single chokepoint for model calls.
- `testing.py` — `MockProvider` for replaying recorded conversations in tests.
- `eval/` — golden-outcome contract loader (`expected.yaml`), grader, reporting.
- `tools/` — `ToolContext`, `ToolSpec`, `read_file`, `read_manifest_node`, and `_lab_filter` (denies agents from reading eval-harness artifacts during diagnosis).
- `_errors.py` — exception hierarchy.

## Public API

```python
from ambesa_core import Incident, FailingModel, FailureClass
from ambesa_core.llm import get_provider, ModelId, CachePolicy
from ambesa_core.eval import grade, load_expected, ExpectedOutcome
```

## Tests

```bash
uv run pytest python/ambesa_core
```

LLM calls in tests go through `MockProvider`, never the live API.
