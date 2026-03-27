import threading


class ThreadLocalBatchCache:
    """Base class for batch-scoped, thread-local caches.

    Subclasses are used as context managers around batch processing.
    The cache is stored in thread-local storage and cleared on exit,
    ensuring no data leaks between batches or threads.

    Usage:
        class MyCache(ThreadLocalBatchCache):
            pass

        with MyCache():
            MyCache.put("key", value)
            cached = MyCache.get("key")
        # cache is cleared here
    """

    _local = threading.local()

    @classmethod
    def _cache_attr(cls):
        return f"_cache_{cls.__name__}"

    @classmethod
    def get(cls, key):
        cache = getattr(cls._local, cls._cache_attr(), None)
        if cache is None:
            return None
        return cache.get(key)

    @classmethod
    def put(cls, key, value):
        cache = getattr(cls._local, cls._cache_attr(), None)
        if cache is not None:
            cache[key] = value

    @classmethod
    def _create(cls):
        setattr(cls._local, cls._cache_attr(), {})

    @classmethod
    def _clear(cls):
        setattr(cls._local, cls._cache_attr(), None)

    def __enter__(self):
        self._create()
        return self

    def __exit__(self, *exc):
        self._clear()
        return False
