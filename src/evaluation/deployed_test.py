from openai import OpenAI

# Initialize client
client = OpenAI(
    base_url="https://vigneshrbusa--research-lineage-serving-serve.modal.run/v1",
    api_key="dummy",
    max_retries=0,
)

def query_research_lineage(user_prompt: str, temperature: float = 0.0) -> dict:
    """
    Send a research lineage analysis prompt to the fine-tuned model.
    
    Args:
        user_prompt: The full prompt containing TARGET paper and CANDIDATE papers
        temperature: 0.0 for deterministic output (recommended)
    
    Returns:
        Parsed JSON response as a dictionary
    """
    import json
    
    response = client.chat.completions.create(
        model="/model-cache/v20260320_184258",
        messages=[
            {"role": "user", "content": user_prompt},
        ],
        timeout=600,
        temperature=temperature,
    )
    
    raw = response.choices[0].message.content
    
    # Parse JSON response
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Sometimes model adds text before/after JSON — extract it
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse JSON from response: {raw[:200]}")


# Example usage
if __name__ == "__main__":
    import json
    
    # Load a training example to test
    with open("train_converted.jsonl", "r") as f:
        example = json.loads(f.readline())
    
    full_text = example["text"]
    user_content = full_text.split("<|im_start|>user\n")[1].split("<|im_end|>")[0]
    
    print(f"Token estimate: {len(user_content)//4}")
    
    result = query_research_lineage(user_content)
    print(json.dumps(result, indent=2))
    print("\nSelected predecessor:", result.get("selected_predecessor_id"))
    print("Breakthrough level:", result.get("target_analysis", {}).get("breakthrough_level"))