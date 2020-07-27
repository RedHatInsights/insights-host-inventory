import os
import tempfile

from prometheus_client import multiprocess


def child_exit(server, worker):
    multiproc_path = os.environ.get("prometheus_mutliproc_dir", tempfile.gettempdir() + "/prometheus-multiproc-dir/")
    multiprocess.mark_process_dead(worker.pid, multiproc_path)
