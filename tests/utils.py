import contextlib
import os
import unittest.mock


@contextlib.contextmanager
def set_environment(new_env=None):
    new_env = new_env or {}
    patched_dict = unittest.mock.patch.dict(os.environ, new_env)
    patched_dict.start()
    os.environ.clear()
    os.environ.update(new_env)
    yield
    patched_dict.stop()
