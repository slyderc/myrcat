"""Services package for Myrcat.

This package contains service classes that provide reusable functionality
across the application. Services encapsulate specific functionality domains
without direct dependencies on managers.
"""

from .image_service import ImageService

__all__ = ['ImageService']