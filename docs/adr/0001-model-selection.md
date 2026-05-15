# ADR 0001: Selection of Qwen3 Models for RAG and Embeddings

## Status
Accepted

## Date
2026-05-14

## Context
The MCP Rust Star Knowledge Server requires a local LLM setup that balances performance, VRAM usage, and accuracy for a multi-project study environment. We need models that handle technical documentation (Rust, C++, Lua) and creative lore effectively.

## Decision
We have selected the following models from the Qwen series:
- **Embedding Model**: `qwen3-embedding:4b`
- **RAG/Chat Model**: `qwen3.5:4b`

## Rationale
- **Local Execution**: Both models are small enough to run on modern consumer hardware with Ollama while providing high-quality results.
- **Technical Proficiency**: The Qwen series is known for strong performance in coding and multi-lingual tasks, which is essential for analyzing Rust Star and FoxOT codebases.
- **Consistency**: Using the same model family for both embeddings and generation often leads to better semantic alignment.

## Consequences
### Positive
- Reduced VRAM footprint compared to larger models (e.g., 7B or 14B).
- Faster inference times for real-time tool use.
- Strong support for the technical languages used in the study projects.

### Negative
- Smaller models may have a slightly lower reasoning ceiling compared to `qwen3.5:9b` or larger.
- Potential for more "concise" answers which might require prompt engineering to expand.
