"""
BatchMixin - Batch processing and progress tracking.

This module re-exports BatchMixin from the batch_controller package for backward compatibility.
The actual implementation is in the batch_controller package.
"""

from app.controllers.batch_controller import BatchMixin

__all__ = ['BatchMixin']
