"""
BatchMixin - Batch processing and progress tracking.

This mixin is inserted in the MRO between ComicTranslateUI and ComicTranslate
so that every method still uses `self` directly—no delegation needed.
"""

from .action_gate import BatchActionGateMixin
from .block_sync import BlockSyncMixin
from .batch_processing import BatchProcessingMixin
from .progress_tracking import ProgressTrackingMixin
from .safety_handler import SafetyHandlerMixin
from .completion_handlers import CompletionHandlersMixin
from .image_handlers import ImageHandlersMixin
from .cancellation_manager import CancellationManager, get_cancellation_manager, check_cancellation, request_batch_cancellation

__all__ = [
    'BatchMixin',
    'BatchActionGateMixin',
    'BlockSyncMixin',
    'BatchProcessingMixin',
    'ProgressTrackingMixin',
    'SafetyHandlerMixin',
    'CompletionHandlersMixin',
    'ImageHandlersMixin',
    'CancellationManager',
    'get_cancellation_manager',
    'check_cancellation',
    'request_batch_cancellation',
]


class BatchMixin(
    BatchActionGateMixin,
    BlockSyncMixin,
    BatchProcessingMixin,
    ProgressTrackingMixin,
    SafetyHandlerMixin,
    CompletionHandlersMixin,
    ImageHandlersMixin,
):
    """Composite mixin combining all batch processing functionality."""
    pass
