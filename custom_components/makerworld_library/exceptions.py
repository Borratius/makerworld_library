"""Exceptions raised by MakerWorld Library."""


class MakerWorldError(Exception):
    """Base exception for MakerWorld communication errors."""


class MakerWorldAuthenticationError(MakerWorldError):
    """The optional MakerWorld/Bambu access token was rejected."""


class MakerWorldConnectionError(MakerWorldError):
    """MakerWorld could not be reached or returned invalid data."""


class MakerWorldRateLimitError(MakerWorldConnectionError):
    """MakerWorld rate-limited the client."""
