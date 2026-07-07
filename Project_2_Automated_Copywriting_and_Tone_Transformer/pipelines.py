import os
import asyncio
import json
import csv
from typing import List, Dict, Any
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from openbatch import BatchCollector
from models import GeneratedCopy
from templates import compile_prompt

# Load environment variables
load_dotenv()

# Setup semaphore for concurrency control (limiting to 10 concurrent requests)
semaphore = asyncio.Semaphore(10)

def get_client_and_model(custom_model: str = None):
    """
    Checks the environment and configures the client and model.
    Prioritizes Groq, then Gemini API, then OpenAI API.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if groq_key:
        # Use Groq API via OpenAI compatibility base URL
        client = AsyncOpenAI(
            api_key=groq_key,
            base_url="https://api.groq.com/openai/v1"
        )
        sync_client = OpenAI(
            api_key=groq_key,
            base_url="https://api.groq.com/openai/v1"
        )
        # Default Groq model is llama-3.3-70b-versatile
        model = custom_model if custom_model else "llama-3.3-70b-versatile"
        # Groq doesn't support OpenAI's batches API, so we treat it similarly to Gemini for fallback execution
        is_batch_supported = False
    elif gemini_key:
        # Use Gemini API via OpenAI compatibility base URL
        client = AsyncOpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        sync_client = OpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        # Default Gemini model is gemini-2.5-flash
        model = custom_model if custom_model else "gemini-2.5-flash"
        is_batch_supported = False
    elif openai_key:
        # Use native OpenAI API
        client = AsyncOpenAI(api_key=openai_key)
        sync_client = OpenAI(api_key=openai_key)
        model = custom_model if custom_model else "gpt-4o-mini"
        is_batch_supported = True
    else:
        # Dry run / Mock client fallback if no keys are found
        client = None
        sync_client = None
        model = "mock-model"
        is_batch_supported = False

    return client, sync_client, model, is_batch_supported

@retry(
    reraise=True,
    stop=stop_after_attempt(7),
    wait=wait_exponential(multiplier=2, min=5, max=60),
)
async def generate_single_copy(client: AsyncOpenAI, prompt: str, model: str, temperature: float, top_p: float, max_tokens: int) -> GeneratedCopy:
    """
    Generates a single marketing copy using AsyncOpenAI and enforces Pydantic structured output.
    Includes rate-limit resilience via Tenacity and concurrency control via Semaphore.
    """
    if client is None:
        # Mock mode fallback when no API keys are provided
        await asyncio.sleep(0.5)  # Simulate network latency
        return GeneratedCopy(
            headline="[Mock] Say Hello to the Next Gen!",
            body="[Mock] This is a mock marketing copy generated because no API keys were configured. Please set GEMINI_API_KEY in your .env file to get real results.",
            call_to_action="[Mock] Try it today!",
            hashtags=["#Mock", "#AI", "#DecodeLabs"]
        )

    async with semaphore:
        try:
            # Enforce structured output via Pydantic model
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a professional marketing copywriter. You must output the response conforming to the requested schema structure."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "top_p": top_p,
                "response_format": GeneratedCopy
            }
            # Adjust token parameters based on model type
            if "gemini" in model.lower() or "gpt-4o" in model.lower() or "o1" in model.lower():
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens

            response = await client.beta.chat.completions.parse(**kwargs)
            return response.choices[0].message.parsed

        except Exception as e:
            # Fallback format for LLMs or proxies that don't support beta.chat.completions.parse fully
            fallback_kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a professional marketing copywriter. You must output ONLY a valid JSON object with the fields: headline (string), body (string), call_to_action (string), hashtags (list of strings). Do not include markdown ticks or wrap in ```json."},
                    {"role": "user", "content": prompt + "\n\nReturn raw JSON only:"}
                ],
                "temperature": temperature,
                "top_p": top_p,
            }
            if "gemini" in model.lower() or "gpt-4o" in model.lower() or "o1" in model.lower():
                fallback_kwargs["max_completion_tokens"] = max_tokens
            else:
                fallback_kwargs["max_tokens"] = max_tokens

            response = await client.chat.completions.create(**fallback_kwargs)
            text = response.choices[0].message.content.strip()
            
            # Clean up markdown block wraps if present
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```json") or lines[0].startswith("```"):
                    lines = lines[1:-1]
                text = "\n".join(lines).strip()

            data = json.loads(text, strict=False)
            return GeneratedCopy(**data)

async def run_realtime_pipeline(product_name: str, description: str, tone: str, platforms: List[tuple], model_name: str = None, temp: float = 0.7, top_p: float = 0.9, max_tokens: int = 300):
    """
    Runs the real-time async pipeline using asyncio.gather to call the API in parallel for all target platforms.
    """
    client, _, model, _ = get_client_and_model(model_name)
    
    if client is None:
        print("[WARNING] Running in MOCK mode (No API Key found). Set GEMINI_API_KEY in .env to run on real API.")

    tasks = []
    for platform, max_chars in platforms:
        prompt = compile_prompt(product_name, description, tone, platform, max_chars)
        tasks.append(generate_single_copy(client, prompt, model, temp, top_p, max_tokens))

    # Run concurrently and match original request indexing
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    output = {}
    for (platform, max_chars), res in zip(platforms, results):
        if isinstance(res, Exception):
            print(f"[ERROR] Copy generation failed for {platform}: {res}")
            output[platform] = {"error": str(res)}
        else:
            output[platform] = res
    return output

def run_bulk_pipeline(csv_path: str, output_prefix: str, model_name: str = None, temp: float = 0.7, top_p: float = 0.9, max_tokens: int = 300):
    """
    Runs the bulk processing pipeline:
    1. Prepares `.jsonl` request file using openbatch BatchCollector.
    2. Submits to OpenAI Batch API if using OpenAI, otherwise runs requests concurrently locally (fallback).
    """
    client, sync_client, model, is_batch_supported = get_client_and_model(model_name)
    
    batch_requests_file = f"{output_prefix}_batch_requests.jsonl"
    collector = BatchCollector(batch_file_path=batch_requests_file)

    # Character limits mapped per platform
    limits = {"linkedin": 3000, "instagram": 2200, "email": 10000, "twitter": 280, "facebook": 5000}

    # Step 1: Write input JSONL file using openbatch
    print(f"[*] Preparing batch request file using openbatch: {batch_requests_file}")
    csv_rows = []
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            csv_rows.append(row)
            product_name = row.get("product_name", "Product")
            description = row.get("description", "")
            tone = row.get("tone", "witty")
            platform = row.get("platform", "linkedin").lower()
            max_chars = limits.get(platform, 2000)

            prompt = compile_prompt(product_name, description, tone, platform, max_chars)
            custom_id = f"req_{i}_{product_name.replace(' ', '_')}_{platform}"

            # Create request structure in openbatch collector
            collector.chat.completions.create(
                custom_id=custom_id,
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional copywriting assistant. Output a raw JSON matching the schema fields: headline, body, call_to_action, hashtags."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temp,
                top_p=top_p,
                max_tokens=max_tokens
            )
            
    print(f"[+] Batch request file successfully generated: {batch_requests_file}")

    # Step 2: Route request
    if is_batch_supported or client is None:
        # For OpenAI keys (or dry run), we can support standard Batch API submission or local runner
        if client is None:
            print("[WARNING] Running bulk pipeline in dry-run/mock mode.")
            print("[+] Simulating bulk result output...")
            # Generate simulated results
            results_file = f"{output_prefix}_results.json"
            mock_results = []
            for row in csv_rows:
                mock_results.append({
                    "product_name": row.get("product_name"),
                    "platform": row.get("platform"),
                    "headline": f"[Mock] Brand New {row.get('product_name')}!",
                    "body": f"[Mock] Get the best ever {row.get('product_name')} now. Specially made with high quality elements.",
                    "call_to_action": "[Mock] Buy now!",
                    "hashtags": ["#AI", "#Mock"]
                })
            with open(results_file, "w", encoding='utf-8') as rf:
                json.dump(mock_results, rf, indent=2)
            print(f"[+] Local simulation results saved to {results_file}")
            return
        
        # If real OpenAI key is set:
        print("[*] Detected OpenAI credentials. Submitting batch job to OpenAI Batch API...")
        try:
            # Upload the file
            with open(batch_requests_file, "rb") as file_data:
                uploaded_file = sync_client.files.create(file=file_data, purpose="batch")
            
            # Submit batch
            batch_job = sync_client.batches.create(
                input_file_id=uploaded_file.id,
                endpoint="/v1/chat/completions",
                completion_window="24h"
            )
            print(f"[+] OpenAI Batch Job submitted successfully!")
            print(f"    - Job ID: {batch_job.id}")
            print(f"    - Status: {batch_job.status}")
            print(f"    - Please poll this job ID via OpenAI API to download results once completed.")
        except Exception as e:
            print(f"[ERROR] Failed to submit to OpenAI Batch API: {e}")
            print("[*] Falling back to executing batch requests locally...")
            is_batch_supported = False # trigger local fallback execution

    if not is_batch_supported:
        # Gemini/Groq do not support OpenAI Batch API. We execute the requests locally in parallel!
        print("[*] Detected Gemini/Groq credentials or Local Fallback. Executing batch requests locally in parallel...")
        results_file = f"{output_prefix}_results.json"
        
        async def process_all_local():
            tasks = []
            for i, row in enumerate(csv_rows):
                product_name = row.get("product_name", "Product")
                description = row.get("description", "")
                tone = row.get("tone", "witty")
                platform = row.get("platform", "linkedin").lower()
                max_chars = limits.get(platform, 2000)

                prompt = compile_prompt(product_name, description, tone, platform, max_chars)
                tasks.append(generate_single_copy(client, prompt, model, temp, top_p, max_tokens))
            
            completed = await asyncio.gather(*tasks, return_exceptions=True)
            
            output_list = []
            for row, res in zip(csv_rows, completed):
                entry = {
                    "product_name": row.get("product_name"),
                    "platform": row.get("platform"),
                    "tone": row.get("tone")
                }
                if isinstance(res, Exception):
                    entry["error"] = str(res)
                else:
                    entry["headline"] = res.headline
                    entry["body"] = res.body
                    entry["call_to_action"] = res.call_to_action
                    entry["hashtags"] = res.hashtags
                output_list.append(entry)
            
            with open(results_file, "w", encoding='utf-8') as rf:
                json.dump(output_list, rf, indent=2)
            print(f"[+] All bulk tasks completed. Results written to: {results_file}")

        asyncio.run(process_all_local())
