from memory_thread.utils.shared_memory import SlabAllocator
import time

def test_logic():
    print("Initializing Allocator...")
    allocator = SlabAllocator(num_slabs=100, slab_size=128)

    print("Reserving 50 slabs...")
    slabs = []
    for i in range(50):
        s = allocator.reserve_slab()
        slabs.append(s)
        # print(f"Reserved {s.slab_id}")

    print("Releasing 50 slabs...")
    for s in slabs:
        allocator.mark_as_written(s.slab_id)
        # Simulate worker reading
        read_slab = allocator.get_written_slab()
        if not read_slab:
            print(f"FAILED to read slab {s.slab_id}")
            break
        allocator.release_slab(read_slab.slab_id)

    print("Done.")
    allocator.validate_invariants()
    print("Invariants passed.")
    allocator.unlink()

if __name__ == "__main__":
    test_logic()
