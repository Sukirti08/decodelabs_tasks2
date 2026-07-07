def compile_prompt(product_name: str, description: str, tone: str, platform: str, max_chars: int) -> str:
    """
    Compiles user variables into a structured master instruction prompt.
    """
    # Enforce strict constraints directly in the template
    template = (
        f"You are a professional copywriter. Your goal is to write high-converting marketing copy.\n\n"
        f"--- INPUTS ---\n"
        f"Product Name: {product_name}\n"
        f"Description: {description}\n"
        f"Target Tone: {tone}\n"
        f"Target Platform: {platform}\n"
        f"Maximum Output Length: {max_chars} characters (including spaces)\n\n"
        f"--- BRAND SAFETY & COPYWRITING INSTRUCTIONS ---\n"
        f"1. Tone Constraint: Adhere strictly to a '{tone}' tone of voice.\n"
        f"2. Platform Style: Tailor the copywriting style for '{platform}'. For example:\n"
        f"   - LinkedIn: Professional, industry-expert tone, bullet points for readability, clear value proposition.\n"
        f"   - Instagram: Visual, engaging hooks, emojis, conversational, strong focus on the hashtags.\n"
        f"   - Twitter/X: Punchy, short sentences, immediate hook, brief call-to-action.\n"
        f"   - Email: Structured subject line (as headline), professional body, and explicit signature/call-to-action.\n"
        f"3. Length Constraint: The total length of the generated copy MUST be under {max_chars} characters. DO NOT exceed this limit.\n"
        f"4. Truthfulness: Do not invent features or properties of the product that are not present in the description.\n"
    )
    return template
