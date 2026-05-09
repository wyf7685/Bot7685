from .kv_store import KVStore


def get_kv_store() -> KVStore:
    from .utils import try_get_caller_plugin

    return KVStore(try_get_caller_plugin().id_)


__all__ = ["get_kv_store"]
