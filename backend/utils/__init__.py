"""Utility functions for the application."""

import math
import json
from typing import Any, Union, Dict, List


def clean_nan_in_data(data: Any) -> Any:
    """
    Recursively clean NaN values from data structures by converting them to None.
    This is necessary because NaN is not valid JSON.
    
    Args:
        data: Any Python data structure (dict, list, tuple, set, or primitive)
    
    Returns:
        Cleaned data structure with NaN replaced by None
    """
    if isinstance(data, dict):
        return {key: clean_nan_in_data(value) for key, value in data.items()}
    elif isinstance(data, (list, tuple, set)):
        return [clean_nan_in_data(item) for item in data]
    elif isinstance(data, float) and math.isnan(data):
        return None
    else:
        return data


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float, returning default if conversion fails or value is NaN/inf.
    
    Args:
        value: Value to convert to float
        default: Default value to return if conversion fails or value is NaN/inf
    
    Returns:
        Float value or default
    """
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (ValueError, TypeError):
        return default
