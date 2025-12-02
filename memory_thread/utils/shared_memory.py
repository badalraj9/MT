import multiprocessing as mp
from multiprocessing.shared_memory import SharedMemory
import ctypes

# Slab states
FREE = 0
RESERVED = 1
WRITTEN = 2
READ = 3
RELEASED = 4

class AlignedSharedMemory:
    """
    A utility class to create a shared memory block with a cache-line-aligned
    memoryview, preventing false sharing between CPU cores.
    """
    def __init__(self, size: int, alignment: int = 64, create=True, name=None):
        self._alignment = alignment
        self._shm = SharedMemory(create=create, size=size + alignment, name=name)

        aligned_address = (self._shm.buf.address + alignment - 1) & -alignment
        offset = aligned_address - self._shm.buf.address
        self.memory = self._shm.buf[offset:offset + size]

    @property
    def name(self):
        return self._shm.name

    def close(self):
        self._shm.close()

    def unlink(self):
        self._shm.unlink()

class SlabHandle:
    def __init__(self, slab_id, memoryview):
        self.slab_id = slab_id
        self.memory = memoryview

class SlabAllocator:
    def __init__(self, num_slabs: int, slab_size: int):
        self.num_slabs = num_slabs
        self.slab_size = slab_size

        # Data Slabs
        self.data_shm = AlignedSharedMemory(size=num_slabs * slab_size)

        # Metadata
        self.metadata_shm = AlignedSharedMemory(size=num_slabs * ctypes.sizeof(ctypes.c_int))
        self.metadata = (ctypes.c_int * num_slabs).from_buffer(self.metadata_shm.memory)
        for i in range(num_slabs):
            self.metadata[i] = FREE

        self.free_list_semaphore = mp.Semaphore(num_slabs)
        self.next_slab = mp.Value(ctypes.c_int, 0)
        self.lock = mp.Lock()

    def reserve_slab(self) -> SlabHandle:
        self.free_list_semaphore.acquire() # Blocks if no free slabs

        with self.lock:
            for i in range(self.num_slabs):
                slab_id = (self.next_slab.value + i) % self.num_slabs
                if self.metadata[slab_id] == FREE:
                    self.metadata[slab_id] = RESERVED
                    self.next_slab.value = (slab_id + 1) % self.num_slabs

                    offset = slab_id * self.slab_size
                    slab_memory = self.data_shm.memory[offset:offset + self.slab_size]
                    return SlabHandle(slab_id, slab_memory)

        # Should not be reached if semaphore logic is correct
        raise Exception("Semaphore acquired but no free slab found.")

    def mark_as_written(self, slab_id: int):
        self.metadata[slab_id] = WRITTEN

    def mark_as_released(self, slab_id: int):
        self.metadata[slab_id] = RELEASED

    def release_slab(self, slab_id: int):
        self.metadata[slab_id] = FREE
        self.free_list_semaphore.release()

    def get_written_slab(self) -> SlabHandle:
        with self.lock:
            for slab_id in range(self.num_slabs):
                if self.metadata[slab_id] == WRITTEN:
                    self.metadata[slab_id] = READ
                    offset = slab_id * self.slab_size
                    slab_memory = self.data_shm.memory[offset:offset + self.slab_size]
                    return SlabHandle(slab_id, slab_memory)
        return None

    def close(self):
        self.data_shm.close()
        self.metadata_shm.close()

    def unlink(self):
        self.data_shm.unlink()
        self.metadata_shm.unlink()
