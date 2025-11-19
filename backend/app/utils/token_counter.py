"""
Token counting utilities for cost estimation
"""

import tiktoken

def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Count tokens in text for a specific model
    
    Args:
        text: Text to count
        model: OpenAI model name
        
    Returns:
        Token count
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to cl100k_base for newer models
        encoding = tiktoken.get_encoding("cl100k_base")
    
    return len(encoding.encode(text))


def estimate_embedding_cost(
    num_tokens: int,
    model: str = "text-embedding-ada-002"
) -> float:
    """
    Estimate cost for embedding generation
    
    OpenAI Pricing (as of 2024):
    - text-embedding-ada-002: $0.0001 per 1K tokens
    
    Args:
        num_tokens: Number of tokens
        model: Embedding model
        
    Returns:
        Estimated cost in USD
    """
    # Pricing per 1K tokens
    pricing = {
        "text-embedding-ada-002": 0.0001,
        "text-embedding-3-small": 0.00002,
        "text-embedding-3-large": 0.00013
    }
    
    price_per_1k = pricing.get(model, 0.0001)
    return (num_tokens / 1000) * price_per_1k


def estimate_chat_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "gpt-3.5-turbo"
) -> float:
    """
    Estimate cost for chat completion
    
    OpenAI Pricing (as of 2024):
    - gpt-3.5-turbo: $0.0015/1K prompt, $0.002/1K completion
    - gpt-4: $0.03/1K prompt, $0.06/1K completion
    
    Args:
        prompt_tokens: Input tokens
        completion_tokens: Output tokens
        model: Chat model
        
    Returns:
        Estimated cost in USD
    """
    pricing = {
        "gpt-3.5-turbo": (0.0015, 0.002),
        "gpt-4": (0.03, 0.06),
        "gpt-4-turbo": (0.01, 0.03)
    }
    
    prompt_price, completion_price = pricing.get(model, (0.0015, 0.002))
    
    prompt_cost = (prompt_tokens / 1000) * prompt_price
    completion_cost = (completion_tokens / 1000) * completion_price
    
    return prompt_cost + completion_cost