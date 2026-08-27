"""F1 telemetry -> apex-to-apex micro-sector feature extraction pipeline.

Phase 1 of the dissertation methodology: data acquisition and pre-processing.
Produces a tabular feature matrix consumable by the Phase 2 OCP (CasADi).
"""

from .config import PipelineConfig

__all__ = ["PipelineConfig", "process_session", "init_cache"]


def __getattr__(name):
    """Lazy import - avoids requiring FastF1 just to use offline components."""
    if name in {"process_session", "init_cache", "process_season", "save_outputs"}:
        from . import pipeline
        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
