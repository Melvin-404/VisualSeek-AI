# Natural Language Query Pipeline

## Overview

The NL Query Pipeline converts free-text surveillance queries into structured search parameters using a multi-stage processing pipeline with LLM-powered intent extraction and robust fallback mechanisms.

## Architecture

```
User Query → Sanitizer → Cache Check → Entity Extractor → Temporal Parser → LLM Intent Extractor → SearchIntent
                                                                                    ↓ (on failure)
                                                                            Local Regex Fallback + CLIP
```

## Components

### 1. `NLUQueryParser` (parser.py)
Main pipeline orchestrator. Handles:
- **Sanitization**: Removes PII (emails, phone numbers, SSNs, credit cards) and SQL/prompt injection attempts before LLM submission.
- **Redis caching**: SHA-256 hash of normalized query → cached SearchIntent (24h TTL).
- **Pipeline assembly**: Calls entity extractor, temporal parser, and LLM extractor in sequence.
- **Fallback**: On LLM failure, falls back to regex-based local parser with `unstructured_fallback=True`, signaling the search engine to use CLIP text embedding.

### 2. `IntentExtractor` (intent.py)
LLM connector supporting three providers:
- **OpenAI** (GPT-4o) — default
- **Anthropic** (Claude 3.5 Sonnet)
- **Llama** (via OpenAI-compatible API endpoint for on-premise deployment)

Features:
- Structured JSON output with `response_format=json_object` (OpenAI)
- Retries with exponential backoff
- Cost tracking per request (USD based on token counts)

### 3. `SpaCyEntityExtractor` (entity_extractor.py)
Local NLP entity extraction using spaCy with rule-based matchers:
- **Colors**: 25+ color terms including compound colors ("dark blue", "neon green")
- **Clothing**: 30+ items (jacket, hat, mask, backpack, etc.)
- **Vehicle types**: 30+ types (sedan, SUV, motorcycle, forklift, etc.)
- **Behaviors**: 40+ action terms (running, loitering, fighting, etc.)
- **Object classes**: Standard COCO classes + surveillance-specific terms
- Falls back to regex extraction if spaCy is unavailable

### 4. `TemporalParser` (temporal_parser.py)
Resolves natural language time expressions to millisecond-epoch ranges:
- Regex fast-path: "last N hours", "today morning", "yesterday evening", "between 9am and 5pm"
- Period mappings: morning (6-12), afternoon (12-17), evening (17-21), night (21-6)
- `dateparser` library fallback for complex expressions
- Timezone-aware (defaults to UTC)

### 5. Prompt Templates
Versioned prompt files in `prompts/`:
- `intent_system.txt`: System prompt with JSON schema, rules, and extraction guidelines
- `intent_fewshot.txt`: 9 few-shot examples covering EN, ES, FR, DE, ZH queries

## SearchIntent Schema

| Field | Type | Description |
|-------|------|-------------|
| `intent_type` | string | `object_search`, `event_search`, `statistical_query`, `comparison` |
| `object_class` | string? | Primary COCO object class (e.g. "person", "car") |
| `attributes` | string[] | Descriptive attributes (e.g. "wearing red jacket") |
| `color` | string? | Primary color of target object |
| `time_range` | dict? | `{start_ms, end_ms, description}` |
| `camera_ids` | string[] | Camera IDs referenced in query |
| `event_type` | string? | Event classification (loitering, fighting, etc.) |
| `spatial_zone` | string? | Named area (parking lot, lobby, etc.) |
| `negations` | string[] | Things that must NOT be present |
| `unstructured_fallback` | bool | True if falling back to CLIP text search |
| `rewritten_query` | string | Expanded query optimized for vector search |
| `llm_cost` | float | API cost in USD |

## Configuration

Set in `.env` or environment variables:

```bash
OPENAI_API_KEY=sk-...           # OpenAI API key
ANTHROPIC_API_KEY=sk-ant-...    # Anthropic API key
LLM_PROVIDER=openai             # openai | anthropic | llama
LLAMA_API_URL=http://...        # Base URL for local Llama endpoint
```

## Multi-Language Support

The pipeline supports queries in:
- 🇺🇸 English
- 🇪🇸 Spanish  
- 🇫🇷 French
- 🇩🇪 German
- 🇨🇳 Chinese

All outputs are normalized to English regardless of input language.

## Example Queries

```python
from app.services.nl_query import NLUQueryParser

parser = NLUQueryParser()

# Object search
intent = await parser.parse("Find people wearing red jackets in the lobby")
# → intent_type="object_search", object_class="person", color="red", attributes=["wearing red jacket"]

# Event search
intent = await parser.parse("Any loitering near emergency exit on cam-006?")
# → intent_type="event_search", event_type="loitering", camera_ids=["cam-006"]

# Statistical query
intent = await parser.parse("How many cars passed through camera 3 today?")
# → intent_type="statistical_query", object_class="car", camera_ids=["cam-003"]

# Multi-language
intent = await parser.parse("有人在停车场打架吗?")
# → intent_type="event_search", event_type="fighting", spatial_zone="parking lot"
```
