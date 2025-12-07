BENCHMARK SPECIFICATION: Phase 3.3 Slab Allocator Stress Test

OBJECTIVE:
Validate that the new slab allocator architecture achieves 5-10x throughput improvement over the old ring buffer system while maintaining memory safety and deterministic behavior under extreme load.

════════════════════════════════════════════════════════════════

PART 1: BASELINE COMPARISON TEST

Instructions:
1. Implement a simple toggle to switch between:
   - OLD_SYSTEM: Ring buffer with pickling
   - NEW_SYSTEM: Slab allocator with zero-copy

2. Use IDENTICAL test data for both systems:
   - 50,000 memory entries
   - Mixed complexity (simple facts, long narratives, entity-rich text)
   - Realistic distribution of text lengths (50-500 chars)

3. Measure for BOTH systems:
   - Total ingestion time (seconds)
   - Throughput (entries per second)
   - CPU utilization per core (%)
   - Memory usage (peak MB)
   - Cache hit rates (embedding, NER)
   - Average latency per entry (ms)
   - P50, P90, P95, P99 latency (ms)

4. Output comparison table:
   | Metric                    | Old (Ring) | New (Slab) | Improvement |
   |---------------------------|------------|------------|-------------|
   | Throughput (eps)          | ???        | ???        | ???x        |
   | Avg latency (ms)          | ???        | ???        | ???x        |
   | CPU utilization (%)       | ???        | ???        | ???         |
   | Memory footprint (MB)     | ???        | ???        | ???         |

PASS CRITERIA:
✅ NEW_SYSTEM >= 3x faster than OLD_SYSTEM
✅ NEW_SYSTEM uses >= 70% CPU (multi-core utilization)
✅ No memory leaks (memory returns to baseline after test)
✅ No data corruption (all 50,000 entries intact)

════════════════════════════════════════════════════════════════

PART 2: CONCURRENCY STRESS TEST

Instructions:
Simulate HIGH CONCURRENT LOAD to find breaking points.

Test Configuration:
- Number of producer processes: 4, 8, 16 (test all three)
- Number of worker processes: 4, 8, 16 (test all three)
- Total test entries: 100,000
- Entry distribution: Random uniform across producers

For each configuration, measure:
1. Sustained throughput (entries/sec over 60 seconds)
2. Backpressure triggering (how often semaphore blocks)
3. Slab allocation failures (any OOM or allocation errors)
4. Worker starvation (any worker idle >100ms)
5. Memory fragmentation (slab free list health)

Output matrix:
| Producers | Workers | Throughput | Backpressure | Errors | Notes |
|-----------|---------|------------|--------------|--------|-------|
| 4         | 4       | ???        | ???%         | ???    | ???   |
| 8         | 4       | ???        | ???%         | ???    | ???   |
| 16        | 8       | ???        | ???%         | ???    | ???   |

PASS CRITERIA:
✅ 4 producers × 4 workers: >= 1,000 eps sustained
✅ 8 producers × 8 workers: >= 1,500 eps sustained
✅ 16 producers × 16 workers: >= 2,000 eps sustained
✅ Zero data loss under any configuration
✅ Zero segmentation faults or memory corruption

════════════════════════════════════════════════════════════════

PART 3: CACHE LINE ALIGNMENT VALIDATION

Instructions:
Verify that cache alignment is actually preventing false sharing.

Test Setup:
1. Use perf (Linux) or Instruments (Mac) to measure:
   - Cache misses per 1000 operations
   - Cache line invalidations
   - MESI protocol state transitions

2. Run with TWO configurations:
   - ALIGNED: Slabs on 64-byte boundaries (your system)
   - MISALIGNED: Slabs on arbitrary boundaries (intentionally broken)

3. Measure cache performance:
   | Metric                          | Aligned | Misaligned | Improvement |
   |---------------------------------|---------|------------|-------------|
   | L1 cache miss rate (%)          | ???     | ???        | ???x        |
   | Cache line invalidations        | ???     | ???        | ???x        |
   | CPU cycles per entry            | ???     | ???        | ???x        |

PASS CRITERIA:
✅ ALIGNED system has 50%+ fewer cache misses than MISALIGNED
✅ Cache line false sharing < 5% of total cache activity
✅ Measurable performance improvement from alignment

════════════════════════════════════════════════════════════════

PART 4: MEMORY SAFETY STRESS TEST

Instructions:
Intentionally try to BREAK the system to validate safety.

Attack Vectors:
1. OVERFLOW ATTACK:
   - Send 1 million entries rapidly (no backpressure respect)
   - Verify semaphore correctly blocks producers
   - Verify no buffer overwrites occur

2. CORRUPTION ATTACK:
   - Randomly kill worker processes mid-operation
   - Verify slabs are properly released back to free list
   - Verify no zombie slabs (allocated but unreachable)

3. RACE CONDITION ATTACK:
   - 32 producers writing simultaneously to same entity
   - Verify atomic state transitions work correctly
   - Verify no lost updates or dirty reads

4. MEMORY LEAK TEST:
   - Run 500,000 entries in batches of 10,000
   - After each batch, check:
     * Free list size returns to initial
     * Memory usage returns to baseline ± 5%
     * No dangling references in metadata array

PASS CRITERIA:
✅ System correctly blocks on semaphore (no overwrites)
✅ Crash recovery: All slabs accounted for after worker death
✅ Race conditions: Zero lost updates, zero corruption
✅ Memory leak: < 0.1% growth per 100k entries

════════════════════════════════════════════════════════════════

PART 5: DETERMINISM VALIDATION

Instructions:
Verify that the system is DETERMINISTIC (same input = same output).

Test Setup:
1. Run the SAME 10,000 entry dataset through the system 10 times
2. For each run, collect:
   - Final state of all entities
   - Order of memory creation
   - Hash of entire memory graph

3. Compare all 10 runs:
   - All entity states IDENTICAL?
   - All memory IDs IDENTICAL?
   - All graph structures IDENTICAL?

PASS CRITERIA:
✅ 100% deterministic: All 10 runs produce identical results
✅ No non-deterministic timestamps/UUIDs in core data
✅ Replay produces same state regardless of timing

════════════════════════════════════════════════════════════════

PART 6: PATHOLOGICAL INPUT TEST

Instructions:
Test edge cases that might break the system.

Input Categories:
1. TINY: 10-char strings (1,000 entries)
2. HUGE: 10,000-char strings (1,000 entries)
3. UNICODE: Emoji-heavy, mixed scripts (1,000 entries)
4. EMPTY: Empty strings, whitespace-only (1,000 entries)
5. DUPLICATE: Same text repeated 10,000 times
6. RAPID: 100,000 entries in <10 seconds burst

For each category, measure:
- Does it crash? (Y/N)
- Does it corrupt data? (Y/N)
- Throughput maintained? (eps)
- Latency spikes? (P99 ms)

PASS CRITERIA:
✅ Zero crashes on any input type
✅ Zero data corruption
✅ Throughput degradation < 20% on pathological inputs
✅ P99 latency < 100ms even on worst inputs

════════════════════════════════════════════════════════════════

FINAL OUTPUT FORMAT:

Please provide results in this structure:

## PHASE 3.3 BENCHMARK RESULTS

### SUMMARY
- Old system throughput: ??? eps
- New system throughput: ??? eps
- **IMPROVEMENT: ???x**
- Target met: ✅ / ❌

### DETAILED METRICS
[Paste all tables from Parts 1-6]

### BOTTLENECK ANALYSIS
What is now the limiting factor?
- CPU? Memory? I/O? Network?
- Where should we optimize next?

### ISSUES FOUND
List any bugs, crashes, or unexpected behaviors

### RECOMMENDATION
Should we proceed to Phase 3.4? Y/N
Reasoning: ???
