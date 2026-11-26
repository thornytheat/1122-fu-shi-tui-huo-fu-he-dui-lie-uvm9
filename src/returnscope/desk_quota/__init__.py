"""复核配额。"""
from .service import evaluate

__all__ = ["evaluate"]

from .service import compare_desk_plans
__all__ += ["compare_desk_plans"]
