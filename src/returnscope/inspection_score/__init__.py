"""验包评分。"""
from .service import evaluate

__all__ = ["evaluate"]

from .service import validate_availability
__all__ += ["validate_availability"]
