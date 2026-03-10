from threading import local


class ThreadLocalBatchCache:
    """Base class for batch-scoped caches backed by ``threading.local``.

    Each subclass gets its own isolated thread-local storage, so multiple
    cache types can coexist without interfering.  Use as a context manager
    around batch processing::

        with MyCache():
            MyCache.get(key)
            MyCache.put(key, value)

    The cache dict is created on ``__enter__`` and cleared on ``__exit__``.
    Outside a context, ``get`` returns ``None`` and ``put`` is a no-op.
    """

    _store: local  # each subclass must define its own

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._store = local()

    def __enter__(self):
        self._store.cache = {}
        return self

    def __exit__(self, *exc):
        self._store.cache = None

    @classmethod
    def get(cls, key):
        cache = getattr(cls._store, "cache", None)
        if cache is not None and key in cache:
            return cache[key]
        return None

    @classmethod
    def put(cls, key, value):
        cache = getattr(cls._store, "cache", None)
        if cache is not None:
            cache[key] = value
