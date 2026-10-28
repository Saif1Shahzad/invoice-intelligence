"""Periodic liveness signal, including while a bounded parsing job is running."""
from contextlib import contextmanager
import threading
from uuid import uuid4
from invoice_intelligence.persistence.operations import OperationsStore

@contextmanager
def heartbeat(store):
    identifier=str(uuid4());operations=OperationsStore(store);stop=threading.Event()
    operations.worker_tick(identifier)
    def tick():
        while not stop.wait(5):
            try: operations.worker_tick(identifier)
            except Exception: pass  # Health expires rather than falsely claiming liveness.
    thread=threading.Thread(target=tick,daemon=True);thread.start()
    try: yield
    finally:
        stop.set();thread.join(timeout=1)
        operations.worker_tick(identifier,state='stopped')
