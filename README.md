# Memory Thread Engine

**Version:** 0.3.1 (Phase 3.3 Active)
**Status:** 🚧 Construction / Benchmarking

## 1. Abstract
The Memory Thread Engine is a sophisticated, long-term cognitive memory subsystem designed as a universal plugin for advanced AI agents. It mimics key aspects of human cognition—contextual retrieval, memory evolution, and explainability—to create a persistent, structured, and context-aware memory layer.

## 2. System Architecture
The engine uses a decoupled, service-oriented architecture built on a hybrid data model.

*   **Vector Store (Qdrant):** High-performance index for semantic search (1536-dim embeddings).
*   **Graph Store (PostgreSQL):** Source of truth for structured `MemoryObjects`, relationships, and metadata.
*   **Ingestion Engine (Phase 3.3):** A new "Slab Allocator" based shared-memory system for zero-copy, high-throughput data intake (replacing older ring buffers/queues).

**Technology Stack:** Python, FastAPI, PostgreSQL (pg_trgm), Qdrant, Pydantic, spaCy, SharedMemory.

---

## 3. Phased Implementation Status

### ✅ Phase 1 & 2: Foundations & Refactoring
*   Established project architecture and Pydantic data models.
*   Implemented hybrid extraction (Regex + spaCy) and classification.

### ✅ Phase 3.1 & 3.2: Retrieval & Basic Optimization
*   **Hybrid Retrieval:** Implemented parallel search (Vector + Keyword) with weighted re-ranking.
*   **Batching:** Implemented batch processing for embeddings and DB inserts.
*   **Status:** Complete.

### 🔄 Phase 3.3: The Throat (Memory Architecture) - **CURRENT FOCUS**
*   **Goal:** Replace `multiprocessing.Queue` with a **Slab Allocator** to achieve 1,500+ entries/sec.
*   **Key Tech:** Cache-line aligned shared memory, zero-copy transfer, lock-free semaphore signaling.
*   **Current Status:** 🐛 **Debugging & Benchmarking**.
    *   Implementing fix for `SlabAllocator` race conditions.
    *   Developing stress-test suite (Concurrency, Determinism, Throughput).

### 📐 Phase 3.4: The Brain (Cognitive Encoding) - **PLANNED**
*   **Goal:** Upgrade from simple classification to a **Truth Maintenance System (TMS)**.
*   **Features:**
    *   **Layer 0:** Meta-Stability (Self-monitoring).
    *   **Layer 1:** Narrative Events (Immutable Causal DAG).
    *   **Layer 2:** State Truth (Derived Reality).
    *   **Layer 3:** Semantic Knowledge (General World Model).
*   **Status:** Designed. Implementation starts after Phase 3.3 verification.

### 📐 Phase 3.5: The Nervous System (Write Pipeline) - **PLANNED**
*   **Goal:** Move from AsyncIO to a **ZeroMQ** "Fire and Forget" pipeline.
*   **Features:** Non-blocking API, independent writer processes, failure isolation.
*   **Status:** Designed. Implementation starts after Phase 3.4.

---

## 4. Technical Details: Phase 3.3 (The Throat)

### Old System (Queue)
*   ❌ Circular buffer / Queue with pickling.
*   ❌ High lock contention.
*   ❌ Throughput limited (~150 eps).

### New System (Slab Allocator)
*   ✅ **Fixed-size memory slabs** (4KB/8KB).
*   ✅ **64-byte cache-line alignment** to prevent false sharing.
*   ✅ **Zero-copy** data transfer between processes.
*   ✅ **Deterministic state machine:** `FREE` → `RESERVED` → `WRITTEN` → `READ` → `RELEASED`.

### Benchmarking Targets
*   **Throughput:** >1,500 entries/sec (10x improvement).
*   **Safety:** Zero deadlocks, zero data corruption under high load.
*   **Determinism:** 100% reproducible output for identical inputs.

---

## 5. Usage

### Running the Server
```bash
uvicorn memory_thread.api.main:app --host 0.0.0.0 --port 8000
```

### Running Benchmarks (Phase 3.3)
```bash
python benchmarks/benchmark_3_3.py
```
*(Note: Benchmark suite currently under development)*
