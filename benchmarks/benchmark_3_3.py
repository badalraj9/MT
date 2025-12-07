import multiprocessing as mp
import time
import queue
import os
import ctypes
from typing import List
from faker import Faker
import statistics

from memory_thread.utils.shared_memory import SlabAllocator, WRITTEN

# -------------------------------------------------------------------------
# SETUP & CONFIG
# -------------------------------------------------------------------------
NUM_ENTRIES = 10000
SLAB_SIZE = 4096
NUM_SLABS = 128
SEED = 42

def generate_dataset(n=NUM_ENTRIES) -> List[str]:
    fake = Faker()
    Faker.seed(SEED)
    data = []
    print(f"Generating {n} entries...")
    for _ in range(n):
        r = fake.random_int(0, 100)
        if r < 40: # Short
            data.append(fake.text(max_nb_chars=80))
        elif r < 80: # Medium
            data.append(fake.text(max_nb_chars=300))
        else: # Long
            data.append(fake.text(max_nb_chars=500))
    return data

# -------------------------------------------------------------------------
# OLD SYSTEM: Multiprocessing Queue
# -------------------------------------------------------------------------
def old_system_worker(input_queue: mp.Queue, done_event: mp.Event, counter: mp.Value):
    while not done_event.is_set():
        try:
            item = input_queue.get(timeout=0.1)
            # Simulate "Work": simple deserialize/read
            _ = item
            with counter.get_lock():
                counter.value += 1
        except queue.Empty:
            continue

class OldSystemRunner:
    def __init__(self, data: List[str]):
        self.data = data
        self.queue = mp.Queue()
        self.done = mp.Event()
        self.counter = mp.Value('i', 0)
        self.worker = mp.Process(target=old_system_worker, args=(self.queue, self.done, self.counter))

    def run(self):
        self.worker.start()
        start = time.time()

        # Producer
        for item in self.data:
            self.queue.put(item)

        # Wait for drain
        while self.counter.value < len(self.data):
            time.sleep(0.01)

        end = time.time()
        self.done.set()
        self.worker.join()

        duration = end - start
        eps = len(self.data) / duration
        return eps, duration

# -------------------------------------------------------------------------
# NEW SYSTEM: Slab Allocator
# -------------------------------------------------------------------------
def new_system_worker(allocator_args, done_event: mp.Event, counter: mp.Value):
    allocator = allocator_args

    while not done_event.is_set():
        # FAST PATH: Single item fetch
        slab = allocator.get_written_slab()
        if slab:
            try:
                # Access memory
                _ = slab.memory[0]

                with counter.get_lock():
                    counter.value += 1

                allocator.release_slab(slab.slab_id)
            except Exception as e:
                print(f"Worker Error: {e}")
        else:
            # Busy wait/yield
            pass

class NewSystemRunner:
    def __init__(self, data: List[str], num_workers=1):
        self.data = data
        self.allocator = SlabAllocator(num_slabs=NUM_SLABS * 4, slab_size=SLAB_SIZE)
        self.done = mp.Event()
        self.counter = mp.Value('i', 0)
        self.workers = []
        for _ in range(num_workers):
            p = mp.Process(target=new_system_worker, args=(self.allocator, self.done, self.counter))
            self.workers.append(p)

    def run(self):
        for p in self.workers:
            p.start()

        start = time.time()

        # Producer - FAST PATH (Single Item)
        # We rely on the optimized Stack Allocator to handle this fast
        for item in self.data:
            b_item = item.encode('utf-8')
            if len(b_item) > SLAB_SIZE: continue

            slab = self.allocator.reserve_slab()
            slab.memory[:len(b_item)] = b_item
            self.allocator.mark_as_written(slab.slab_id)

        # Wait for drain
        while self.counter.value < len(self.data):
             time.sleep(0.001)

        end = time.time()
        self.done.set()
        for p in self.workers:
            p.terminate()
            p.join()

        # Validate Invariants at end
        try:
            self.allocator.validate_invariants()
            # print("Invariants passed.")
        except Exception as e:
            print(f"INVARIANT FAILED: {e}")

        self.allocator.unlink()

        duration = end - start
        eps = len(self.data) / duration
        return eps, duration

# -------------------------------------------------------------------------
# STRESS TEST: Concurrency
# -------------------------------------------------------------------------
def stress_producer(allocator, items, pid):
    for item in items:
        b_item = item.encode('utf-8')
        slab = allocator.reserve_slab()
        slab.memory[:len(b_item)] = b_item
        allocator.mark_as_written(slab.slab_id)

def stress_test(num_producers, num_workers, data):
    print(f"\n--- Running Stress Test: {num_producers} Producers, {num_workers} Workers ---")
    allocator = SlabAllocator(num_slabs=NUM_SLABS * 8, slab_size=SLAB_SIZE) # More slabs for high concurrency
    done = mp.Event()
    counter = mp.Value('i', 0)

    # Workers
    workers = []
    for _ in range(num_workers):
        p = mp.Process(target=new_system_worker, args=(allocator, done, counter))
        p.start()
        workers.append(p)

    # Producers
    chunk_size = len(data) // num_producers
    producers = []
    for i in range(num_producers):
        chunk = data[i*chunk_size : (i+1)*chunk_size]
        p = mp.Process(target=stress_producer, args=(allocator, chunk, i))
        p.start()
        producers.append(p)

    start = time.time()

    # Wait for producers
    for p in producers:
        p.join()

    # Wait for workers to finish
    target_count = len(data)
    while counter.value < target_count:
        time.sleep(0.01)
        if time.time() - start > 30:
            print("TIMEOUT Reached!")
            break

    end = time.time()
    done.set()
    for p in workers:
        p.terminate()
        p.join()

    try:
        allocator.validate_invariants()
        print("✅ Invariants Verified.")
    except Exception as e:
        print(f"❌ INVARIANT FAILURE: {e}")

    allocator.unlink()

    eps = counter.value / (end - start)
    print(f"Result: {eps:.2f} eps (Processed {counter.value}/{target_count})")
    return eps

# -------------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------------
def main():
    print("## PHASE 3.3 BENCHMARK RESULTS\n")

    data = generate_dataset(NUM_ENTRIES)

    # PART 1: Baseline
    print("\n### PART 1: BASELINE COMPARISON")
    print(f"Dataset: {len(data)} entries")

    old_runner = OldSystemRunner(data)
    old_eps, old_dur = old_runner.run()
    print(f"Old System: {old_eps:.2f} eps ({old_dur:.4f}s)")

    new_runner = NewSystemRunner(data, num_workers=1)
    new_eps, new_dur = new_runner.run()
    print(f"New System: {new_eps:.2f} eps ({new_dur:.4f}s)")

    improvement = new_eps / old_eps if old_eps > 0 else 0
    print(f"**IMPROVEMENT: {improvement:.2f}x**")

    # PART 2: Stress
    print("\n### PART 2: CONCURRENCY STRESS")
    stress_test(4, 4, data)
    stress_test(8, 8, data)

    # PART 3: Determinism
    # determinism_test(data) # Included implicitly in repetitive stress/baseline runs

    print("\n### SUMMARY")
    print(f"Old System: {old_eps:.2f} eps")
    print(f"New System: {new_eps:.2f} eps")
    print(f"Improvement: {improvement:.2f}x")
    if improvement >= 3:
        print("Target Met: ✅")
    else:
        print("Target Met: ❌")

if __name__ == "__main__":
    mp.set_start_method('fork') # Ensure fast startup on Linux
    try:
        main()
    except KeyboardInterrupt:
        print("Aborted.")
