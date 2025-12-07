# Memory Thread Engine

## Project Overview

The Memory Thread Engine is a deterministic, high-throughput ingestion and retrieval system for semantic memory. It is built on a foundation of rule-based pipelines, caches, embeddings, NER, routing, Postgres, and Qdrant. The engine is designed to be model-free, CPU-only, and to provide explainable, deterministic behavior.

## Phases

### Phase 3.3: The Throat (Core Hardening & High-Performance I/O)

This phase focuses on replacing standard data passing with a zero-copy shared memory architecture to maximize CPU efficiency and build the core data processing and storage pipelines.

### Phase 3.4: The Brain (N-Gram Profiling & Adaptive Routing)

This phase implements an intelligent, deterministic routing engine to classify text and select the most efficient processing pipeline, minimizing unnecessary computation.

### Phase 3.5: The Nervous System (Production Hardening)

This phase replaces standard inter-process queues with a lock-free messaging pipeline and adds production-ready features like persistent caching and autoscaling.

### Phase 4: Cognition Layer (Future)

This future phase will introduce a cognition layer for pruning, merging, assimilation, and adaptation of memories.

## Developer's Diary

### The "Elite Upgrades"

Our initial design for Phase 3.3 used a standard `ProcessPoolExecutor` with a shared memory ring buffer. While this was a step in the right direction, we quickly realized that it had several flaws that would prevent us from reaching our performance goals. The variable-length writes, lack of true backpressure, and the potential for race conditions made the system both non-deterministic and unsafe.

To address these issues, we pivoted to the "Elite Upgrades," a set of advanced architectural patterns that would form the foundation of a truly high-performance system:

*   **Fixed-Size, Cache-Line-Aligned Slab Memory:** We replaced the ring buffer with a pool of fixed-size, cache-line-aligned memory slabs. This eliminates fragmentation, prevents false sharing, and provides a much more predictable and performant memory layout.
*   **Semaphore-Guarded Free List:** We introduced a semaphore to manage the pool of free slabs. This provides true backpressure, blocking the ingestion process when no slabs are available and preventing the system from being overwhelmed.
*   **ZeroMQ (ZMQ) Pipeline:** We replaced the standard `multiprocessing.Queue` with a lock-free ZeroMQ pipeline for asynchronous database writes. This decouples the CPU-bound worker processes from the I/O-bound database writer, allowing the ingestion API to stay open 100% of the time.

### The Debugging Journey

Implementing these advanced patterns was not without its challenges. We encountered a series of subtle bugs and deadlocks that required a systematic and thorough debugging process. Our journey to a stable system involved:

1.  **Isolating the Producer:** We started by disabling the worker and database writer processes to test the producer logic in isolation. This allowed us to verify that the slab allocation and writing process was working correctly.
2.  **Creating an Isolated Worker Test:** We then created a separate test script to test the worker lifecycle in isolation. This allowed us to find and fix a critical bug in the slab release logic that was causing a deadlock.
3.  **Tracing Slab State:** Throughout the process, we added extensive logging to trace the state of the slabs and the semaphore count. This gave us a clear, step-by-step view of the resource management logic and helped us pinpoint the exact cause of the deadlocks.

Through this iterative process, we were able to build a robust and performant system that meets the demanding requirements of the Memory Thread Engine.
