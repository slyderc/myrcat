"""Custom exceptions for Myrcat."""


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