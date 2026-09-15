class CacheSerializationError(Exception):
    """A cache value could not be serialized."""


class CacheDeserializationError(Exception):
    """A cached value could not be deserialized."""


__all__ = ["CacheDeserializationError", "CacheSerializationError"]
