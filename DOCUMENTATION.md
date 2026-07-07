# Technical Documentation: Automated Copywriting & Tone Transformer

This document provides a detailed technical reference of the codebase, components, configuration parameters, and extensibility guidelines for the Automated Copywriting & Tone Transformer application.

---

## Codebase Reference

### 1. Data Models (`models.py`)
Uses `pydantic` to enforce structured outputs from the language models. This ensures that downstream consumers (e.g., automated database inserters, social posting APIs) can rely on a consistent JSON structure.

#### `GeneratedCopy` (Pydantic Model)
Defines the schema for the generated marketing copy:
*   `headline` (string): Captures user attention. Custom-tailored to the target platform (e.g., subject line format for emails, punchy headers for Twitter/X).
*   `body` (string): The primary marketing content containing the product value proposition and descriptions.
*   `call_to_action` (string): The explicit next step for the reader (e.g., link invitation, sign-up prompt).
*   `hashtags` (list of strings): A list of 3–5 relevant, platform-optimized hashtags.

---

### 2. Prompt Compilation Engine (`templates.py`)
Responsible for isolating raw user inputs and embedding them securely into a structured instruction prompt. It acts as the "Gatekeeper" ensuring brand safety guidelines and platform rules are strictly adhered to.

#### `compile_prompt` (Function)
Combines variables into the master instruction prompt:
- **Inputs**: `product_name`, `description`, `tone`, `platform`, `max_chars`.
- **System Constraints**:
  - Directs model to remain truthful (no feature hallucination).
  - Inject length limits directly into the prompt instructing the LLM to count character lengths.
  - Tailor output format to specific platform guidelines (bullet points for LinkedIn, emojis/hooks for Instagram, etc.).

---

### 3. Execution Pipelines (`pipelines.py`)
Orchestrates API client initialization, concurrency limits, rate-limit retries, and dual-pipeline routing.

#### Multi-Provider Client Setup (`get_client_and_model`)
Dynamically parses environment variables to configure the active client. It prioritizes API keys in the following order:
1.  **Groq API**: Sets `base_url="https://api.groq.com/openai/v1"` and defaults to `llama-3.3-70b-versatile`.
2.  **Gemini API**: Sets `base_url="https://generativelanguage.googleapis.com/v1beta/openai/"` and defaults to `gemini-2.5-flash`.
3.  **OpenAI API**: Uses standard base URL and defaults to `gpt-4o-mini`.
4.  **Dry-run (Mock Mode)**: Used when no credentials exist. Generates mock responses.

#### Concurrency and Resiliency Mechanisms
- **`asyncio.Semaphore(10)`**: Limits active concurrent API connections to 10. Prevents triggering server-side instant rate-limits (HTTP 429).
- **`tenacity` Retry Logic**:
  - Decorates `generate_single_copy` with exponential retry backoff.
  - Configured with `multiplier=2`, `min=5` seconds, and `max=60` seconds, with a maximum of `7` retry attempts. This is highly effective at waiting out resource exhaustion quotas, especially on free tier accounts.

#### JSON Parsing Fault Tolerance
To ensure stability against erratic formatting from smaller open-source models, the parsing routine:
1.  Attempts structured output parsing via `client.beta.chat.completions.parse`.
2.  Falls back to standard text completion if the API throws a parsing error, requesting raw JSON in the system message.
3.  Parses text blocks by stripping markdown formatting (` ```json ` wrapper) and using `json.loads(text, strict=False)`. Specifying `strict=False` permits literal unescaped control characters (such as newlines `\n` or tabs) within string properties.

#### Bulk Pipeline Routing
- **Standard (OpenAI)**: Uploads the `openbatch` generated `.jsonl` file directly to OpenAI Batch API and initiates a batch job.
- **Fallback (Groq / Gemini)**: Reads the generated `.jsonl` file and executes the batch queries concurrently locally using the async pipeline, compiling results into a final `copy_bulk_results.json` output file.

---

### 4. CLI Entry Point (`run.py`)
Sets up argument parsing and routes actions based on user input.

#### Custom Argparse Configuration
- **`prefix_chars="-+"`**: Enables the use of both standard `-` flags and custom `+` action flags.
- **`+a <platform>`**: Captured via `platform_converter` type validation. It verifies that the inputted platform is valid and binds it to its standard character limit in a structured tuple `(platform_name, limit)`.
- **CSV trigger**: If the `--csv` flag is provided, the script skips real-time processing and routes execution to the bulk pipeline.

---

## Extensibility Guide

### How to Add a New Platform
To add support for a new social media platform:
1.  Open `run.py`.
2.  Locate `platform_converter` function.
3.  Add the new platform name to the `valid_platforms` set (lowercase).
4.  Define its maximum character constraint in the `limits` dictionary:
    ```python
    limits = {
        ...,
        "tiktok": 150,  # Example platform addition
    }
    ```
5.  (Optional) Add platform-specific styling guidelines to the prompt template inside `templates.py`.

### How to Support a New Provider
To add a new API provider:
1.  Open `pipelines.py`.
2.  Locate `get_client_and_model` function.
3.  Check for the provider's API key in the environment:
    ```python
    provider_key = os.getenv("NEW_PROVIDER_API_KEY")
    ```
4.  Configure the `AsyncOpenAI` and `OpenAI` clients with the provider's endpoint URL:
    ```python
    client = AsyncOpenAI(
        api_key=provider_key,
        base_url="https://api.newprovider.com/v1"
    )
    ```
5.  Set `is_batch_supported` to `True` or `False` depending on if they support standard OpenAI Batch API protocols.
