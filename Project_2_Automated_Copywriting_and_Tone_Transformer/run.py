import argparse
import asyncio
import sys
from pipelines import run_realtime_pipeline, run_bulk_pipeline

def platform_converter(value: str) -> tuple:
    """
    Custom type converter that intercepts platform inputs and parses them
    directly into structured tuples (platform_name, character_limit).
    """
    valid_platforms = {"linkedin", "instagram", "email", "twitter", "facebook"}
    platform_lower = value.lower().strip()
    
    if platform_lower not in valid_platforms:
        raise argparse.ArgumentTypeError(
            f"Invalid platform '{value}'. Must be one of: {', '.join(valid_platforms)}"
        )
        
    # Standard character limits described in the requirements
    limits = {
        "linkedin": 3000,
        "instagram": 2200,
        "email": 10000,
        "twitter": 280,
        "facebook": 5000
    }
    
    return (platform_lower, limits[platform_lower])

def main():
    # Enforce support for both standard (-) and custom (+) prefix flags
    parser = argparse.ArgumentParser(
        description="Automated Copywriting & Tone Transformer CLI",
        prefix_chars="-+"
    )

    # Standard configuration flags
    parser.add_argument("--product", type=str, help="The name of the product")
    parser.add_argument("--description", type=str, help="Raw product description/facts")
    parser.add_argument("--tone", type=str, default="witty", help="Tone of the copy (e.g. witty, professional, bold)")
    parser.add_argument("--model", type=str, default=None, help="Specific LLM model to target (defaults based on API key)")
    parser.add_argument("--temperature", type=float, default=0.7, help="Creativity temperature (0.0 to 1.0)")
    parser.add_argument("--top-p", type=float, default=0.9, help="Top-P nucleus sampling parameter")
    parser.add_argument("--max-tokens", type=int, default=300, help="Max tokens generated per request")

    # Custom action flag using '+' prefix char
    parser.add_argument(
        "+a",
        dest="platforms",
        type=platform_converter,
        action="append",
        help="Custom action: Add a target platform (e.g., +a linkedin, +a twitter)"
    )

    # Bulk processing input
    parser.add_argument("--csv", type=str, help="Path to input CSV for bulk generation")
    parser.add_argument("--output-prefix", type=str, default="copy_bulk", help="Prefix for batch files and results")

    args = parser.parse_args()

    # Route execution based on inputs
    if args.csv:
        print(f"[*] Starting Bulk Processing Pipeline for CSV: {args.csv}")
        run_bulk_pipeline(
            csv_path=args.csv,
            output_prefix=args.output_prefix,
            model_name=args.model,
            temp=args.temperature,
            top_p=args.top_p,
            max_tokens=args.max_tokens
        )
    else:
        # For real-time generation, require product name, description, and platforms
        if not args.product or not args.description or not args.platforms:
            print("[ERROR] Real-time generation requires --product, --description, and at least one +a <platform> flag.")
            print("        Example: python run.py --product 'Shoe' --description 'Comfortable sneaker' --tone witty +a linkedin +a twitter")
            parser.print_help()
            sys.exit(1)

        print(f"[*] Starting Real-time Async Pipeline for {args.product}...")
        results = asyncio.run(
            run_realtime_pipeline(
                product_name=args.product,
                description=args.description,
                tone=args.tone,
                platforms=args.platforms,
                model_name=args.model,
                temp=args.temperature,
                top_p=args.top_p,
                max_tokens=args.max_tokens
            )
        )

        print("\n=== GENERATED COPY RESULTS ===")
        for platform, copy in results.items():
            print(f"\n--- Platform: {platform.upper()} ---")
            if isinstance(copy, dict) and "error" in copy:
                print(f"Error generating copy: {copy['error']}")
            else:
                print(f"HEADLINE: {copy.headline}")
                print(f"BODY:\n{copy.body}")
                print(f"CTA: {copy.call_to_action}")
                print(f"HASHTAGS: {' '.join(copy.hashtags)}")
        print("===============================\n")

if __name__ == "__main__":
    main()
