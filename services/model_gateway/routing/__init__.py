"""Model Gateway — routing layer"""
from .model_registry import ModelRegistry, get_model_registry
from .model_selector import ModelSelector, SelectionResult, get_model_selector
from .fallback_manager import FallbackManager, get_fallback_manager

__all__ = [
    "ModelRegistry",
    "get_model_registry",
    "ModelSelector",
    "SelectionResult",
    "get_model_selector",
    "FallbackManager",
    "get_fallback_manager",
]
