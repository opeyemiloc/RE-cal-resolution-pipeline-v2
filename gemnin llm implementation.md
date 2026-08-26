# Gemini LLM API Implementation

This document outlines how the Gemini API is implemented for the Entity Resolution pipeline in this project.

## Overview
The LLM resolution component is located at `src/resolution/llm_resolver.py`. It uses the official `google-genai` Python SDK to communicate with Gemini models. The LLM acts as the final decision maker when traditional fuzzy matching fails to confidently match an ambiguous shipping name to a master account.

## Key Implementation Details

1. **SDK Used**: We use `from google import genai` and initialize the client simply with `client = genai.Client()`. The client automatically picks up the `GEMINI_API_KEY` from the environment variables.
2. **Model Configuration**: The model version (e.g., `gemini-3.6-flash` or `gemini-3.5-flash`) and batch size are configurable via `config.yaml` or through the Streamlit UI's advanced settings (`app.py`).
3. **Batching Strategy**: 
   - Instead of sending one record per API call, candidates are grouped into batches (configured via `batch_size`, default 5).
   - This approach is significantly more efficient, reducing total network overhead and staying well within API rate limits while saving time.
   - The batch is structured as a clear list of records inside a single prompt.
4. **Resiliency and Retries**: 
   - We use the `tenacity` library's `@retry` decorator for `_call_gemini_with_retry`.
   - It performs exponential backoff (min 5 seconds, max 60 seconds) and stops after 5 attempts.
   - This is crucial for handling transient issues like API `429 Quota Exceeded` errors gracefully.
5. **Prompt Engineering & Schema**:
   - The prompt provides explicit rules for matching (e.g., handling extra words like 'LIMITED', matching core brand).
   - We inject the Pydantic JSON schema of the `LLMMatchDecision` model directly into the prompt using `json.dumps(LLMMatchDecision.model_json_schema(), indent=4)`. This forces Gemini to respond strictly with an array of structured JSON objects matching our expected Python types.
6. **Robust Parsing**:
   - The response parsing explicitly strips markdown artifacts (like ```json ... ```).
   - It ensures the response is an array and iterates over the items, gracefully mapping confidence scores (scaling float up to 100 or parsing int appropriately) back into strongly typed `LLMMatchDecision` instances.
   - If a batch completely fails (e.g., unparseable JSON), the script safely catches the exception and fails all records in that specific batch with a detailed reasoning string rather than crashing the entire pipeline.
7. **Rate Limiting**:
   - In addition to tenacity retries, there is a polite baseline sleep (`time.sleep(2)`) between batches to avoid spamming the Gemini endpoint and triggering rate limit blocks unnecessarily.
