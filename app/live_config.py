"""Validated private-workflow limits; no dotenv loading or provider imports."""

import os
import re


def bounded_integer(name: str, default: int, maximum: int, minimum: int = 0) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    if not re.fullmatch(r"[0-9]+", value.strip()):
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}.")
    try:
        number = int(value.strip())
    except ValueError:
        raise ValueError(f"{name} is invalid.") from None
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}.")
    return number


def max_search_jobs() -> int:
    return bounded_integer("MAX_SEARCH_JOBS", default=10, minimum=1, maximum=10)


def openai_max_retries() -> int:
    # Two retries preserves the previous OpenAI SDK default.
    return bounded_integer("OPENAI_MAX_RETRIES", default=2, maximum=2)


def tavily_max_results() -> int:
    return bounded_integer("TAVILY_MAX_RESULTS", default=5, minimum=1, maximum=20)
