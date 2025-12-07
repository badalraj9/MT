from multiprocessing.shared_memory import SharedMemory

class MisalignedSharedMemory:
    """
    An intentionally misaligned shared memory block for testing purposes.
    """
    def __init__(self, size: int, create=True, name=None):
        self._shm = SharedMemory(create=create, size=size, name=name)
        self.memory = self._shm.buf

    @property
    def name(self):
        return self._shm.name

    def close(self):
        self._shm.close()

    def unlink(self):
        self._shm.unlink()
