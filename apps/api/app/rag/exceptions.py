class RAGError(Exception):
    """Base error for document ingestion and retrieval."""


class DependencyUnavailableError(RAGError):
    """Raised when an optional provider dependency is not installed."""


class DocumentValidationError(RAGError):
    """Raised when an uploaded document cannot be safely indexed."""


class ProviderConfigurationError(RAGError):
    """Raised when a configured AI provider is missing required settings."""
