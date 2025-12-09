# Memory Thread Engine

**Version:** 0.6.0 (Phase 6 Complete)
**Status:** ✅ Operational / 🛠️ Phase 7 Pending

## 1. Abstract
The Memory Thread Engine is a sophisticated, long-term cognitive memory subsystem designed as a universal plugin for advanced AI agents. It mimics key aspects of human cognition—contextual retrieval, memory evolution, biological decay, and explainability—to create a persistent, structured, and context-aware memory layer.

## 2. System Architecture
The engine uses a decoupled, service-oriented architecture built on a hybrid data model.

*   **Vector Store (Qdrant):** High-performance index for semantic search (1536-dim embeddings).
*   **Graph Store (PostgreSQL):** Source of truth for structured `MemoryObjects`, relationships, immutable event logs, and metadata.
*   **Ingestion Fabric (Phase 4):** A distributed ZeroMQ `ROUTER`/`DEALER` spine enabling horizontal scaling and backpressure management.
*   **Cognitive Brain (Phase 3.4):** A Truth Maintenance System (TMS) implementing Event Sourcing (Layer 1 Events -> Layer 2 State).
*   **Cognitive Maintenance (Phase 5):** Background services for Identity Merging, Event Assimilation, Pruning, and Memory Decay.
*   **Cognitive Correctness (Phase 6):** Deterministic Replay, Snapshotting, and Timewarp Correction for absolute data integrity.

**Technology Stack:** Python, FastAPI, PostgreSQL (pg_trgm), Qdrant, Pydantic, spaCy, ZeroMQ, aiokafka.

---

## 3. Phased Implementation Status

### ✅ Phase 1 & 2: Foundations
*   Core data models and hybrid extraction (Regex + spaCy).

### ✅ Phase 3: The Core Engine
*   **3.1/3.2 Retrieval:** Hybrid Search (Vector + Keyword) with weighted scoring.
*   **3.3 The Throat:** `SlabAllocator` shared-memory ingestion (10x speedup).
*   **3.4 The Brain (TMS):** Event Sourcing architecture. Immutable Events lead to Derived State.
*   **3.5 The Nervous System:** ZeroMQ Pipeline to decouple ingestion from persistence.

### ✅ Phase 4: Distributed Ingestion
*   **Ingestion Gateway:** High-throughput entry point.
*   **Smart Fabric:** ZMQ Router/Dealer with bidirectional backpressure.
*   **Performance:** Benchmarked at **~47,000 events/sec**.

### ✅ Phase 5: Cognitive Maintenance (The Living Memory)
*   **Identity Service:** Detects and merges duplicate entities (e.g., "John" + "J. Smith").
*   **Assimilation Engine:** Compresses repetitive events (100x "Add 1" -> 1x "Add 100") while preserving provenance.
*   **Pruner Service:** Removes low-value, derived states to keep working memory lean.
*   **Decay Engine:** Implements biological forgetting curves (Freshness = e^-λt).

### ✅ Phase 6: Cognitive Correctness (Reliability)
*   **Replay Debugger:** Deterministically replays event logs to verify state correctness (`nebula replay`).
*   **Snapshot Service:** Creates periodic state checkpoints for instant loading (`nebula snapshot`).
*   **Timewarp Engine:** Handles out-of-order/late events by inserting them into the timeline and recomputing state.
*   **Ancestry Cache:** Optimizes provenance queries.

### 📐 Phase 7: Knowledge Graph & Reasoning - **PLANNED**
*   **Goal:** Add multi-hop reasoning capabilities.
*   **Features:**
    *   Graph Database (Entities + Relations).
    *   Multi-Hop Query Engine (Pathfinding).
    *   Hybrid Retrieval (Vector + Graph + Truth).
*   **Status:** Next on Roadmap.

---

## 4. Key Components

### Truth Maintenance System (TMS)
Ensures that the "Current State" of an entity is always a pure function of its history.
- **Layer 0:** Meta-Stability (Self-monitoring for drift).
- **Layer 1:** Narrative Events (Immutable, append-only log).
- **Layer 2:** State Truth (Derived reality, versioned).

### Distributed Fabric
Replaces simple queues with a "Smart Spine".
- **Backpressure:** Producers are throttled if the database slows down.
- **Spillover:** Disk-backed buffers prevent memory overflows.
- **Durability:** Async Kafka mirroring ensures no data loss.

---

## 5. Usage

### Running the Server
```bash
uvicorn memory_thread.api.main:app --host 0.0.0.0 --port 8000
```

### CLI Tools (Nebula)

**Replay Debugger (Phase 6.1):**
```bash
# Capture a golden trace for debugging
python -m memory_thread.cli.replay capture --entity-id <UUID> --output trace.json

# Verify that logic changes haven't broken history
python -m memory_thread.cli.replay verify --trace trace.json
```

**Snapshot Management (Phase 6.2):**
```bash
python -m memory_thread.cli.phase6 snapshot create --entity-id <UUID>
python -m memory_thread.cli.phase6 snapshot restore --entity-id <UUID>
```

**Timewarp Injection (Phase 6.4):**
```bash
# Insert a late event (e.g., arrived 10 minutes late)
python -m memory_thread.cli.phase6 timewarp insert --entity-id <UUID> --minutes-ago 10 --action ADD --delta-json '{"count": 1}'
```

### Running Benchmarks
```bash
# Phase 3.4 (TMS Throughput)
python benchmarks/benchmark_3_4.py

# Phase 4.1 (Distributed Ingestion)
python benchmarks/benchmark_phase_4_1.py

# Phase 5 (Robustness & Scale - 100k)
python benchmarks/benchmark_phase_5_robust.py
```
