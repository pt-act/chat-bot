# PR Draft 5

**Branch:** `audit/graph-integration-test` (stacked on `audit/synthesized-isolation`) → `main`
**Title:** `test(graph): end-to-end integration test through the real get_llm path`

> Draft only — not pushed. Apply after PRs 1–4.

## Why

The original critical bug (C-1) was a guaranteed runtime `TypeError` on the main
`/chat` path — the nodes called `get_llm(temperature=…, max_tokens=…)` but `get_llm()`
took no arguments. It carried **96% coverage** because every unit test mocked
`_get_chat`, so the real wiring was never exercised. This adds the missing coverage.

## Change

- **`tests/test_graph_integration.py`:** compiles the real `build_graph()` pipeline and
  invokes it, mocking only the outer boundaries — the provider SDK (`langchain_openai.ChatOpenAI`),
  Redis (`fakeredis`), and the vector store. It drives the **real**
  `utils.llm_adapter.get_llm(temperature, max_tokens)` call and asserts:
  1. the pipeline completes and returns the model's answer end-to-end;
  2. `ChatOpenAI` was constructed with `temperature`/`max_tokens` (proves `get_llm`
     accepted and forwarded them — the exact C-1 failure);
  3. memory was persisted under the namespaced key `chat:memory:itest` (M-4).

Run against pre-fix `utils/llm_adapter.py`, this test fails with `TypeError`, i.e. it
would have caught C-1.

## Validation

```
pytest -q   # 162 passed, 0 failed (97.8% coverage)
```
