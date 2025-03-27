"""Custom exceptions for Myrcat.

This module defines a hierarchy of exceptions used throughout the application.
All exceptions inherit from the base MyrcatException to allow for:

1. Easy catching of all application-specific exceptions
2. Consistent error handling patterns
3. Clear error messages for troubleshooting

When raising exceptions, prefer using the most specific exception type
that matches the error condition.
"""


class MyrcatException(Exception):
    """Base exception for all Myrcat errors."""
    pass


class ConfigurationError(MyrcatException):
    """Raised for configuration-related errors."""
    pass


class ValidationError(MyrcatException):
    """Raised for data validation errors."""
    pass


class ConnectionError(MyrcatException):
    """Raised for server connection errors."""
    pass


class SocialMediaError(MyrcatException):
    """Raised for social media integration errors."""
    pass


class DatabaseError(MyrcatException):
    """Raised for database operation errors."""
    pass


class ArtworkError(MyrcatException):
    """Raised for artwork file operation errors."""
    pass


class ContentGenerationError(MyrcatException):
    """Raised for AI content generation errors."""
    pass


class AnalyticsError(MyrcatException):
    """Raised for social media analytics errors."""
    pass