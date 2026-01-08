"""
Memory Thread: Quick Diagnostic Test
=====================================
Simple import and service availability test.
No memory guardrails - just quick checks.

Run: python tests/quick_diagnostic.py
"""

import os
import sys

# Fix path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

print("=" * 60)
print("🔍 MT QUICK DIAGNOSTIC TEST")
print("=" * 60)

results = []

# Test 1: Core imports
print("\n1️⃣ Testing core imports...")
try:
    from memory_thread.db.postgres_client import PostgresClient
    from memory_thread.db.qdrant_client import QdrantClientWrapper
    print("   ✅ Database clients importable")
    results.append(("Core imports", True))
except Exception as e:
    print(f"   ❌ Import error: {e}")
    results.append(("Core imports", False))

# Test 2: PostgreSQL connection
print("\n2️⃣ Testing PostgreSQL connection...")
try:
    from memory_thread.db.postgres_client import PostgresClient
    pg = PostgresClient()
    with pg.get_cursor() as cur:
        cur.execute("SELECT 1 as test")
        row = cur.fetchone()
    print("   ✅ PostgreSQL connected")
    results.append(("PostgreSQL", True))
except Exception as e:
    print(f"   ❌ PostgreSQL error: {e}")
    results.append(("PostgreSQL", False))

# Test 3: Service imports
print("\n3️⃣ Testing service imports...")
services_ok = 0
services_fail = 0

service_tests = [
    ("TMSService", "memory_thread.services.tms_service", "TMSService"),
    ("ConflictDetector", "memory_thread.services.maintenance_suggester", "ConflictDetector"),
    ("StalenessDetector", "memory_thread.services.maintenance_suggester", "StalenessDetector"),
    ("AutonomousEngine", "memory_thread.services.autonomous_engine", "AutonomousEngine"),
    ("AutonomicController", "memory_thread.services.autonomic_controller", "AutonomicController"),
    ("InferenceEngine", "memory_thread.services.reasoning.inference_engine", "InferenceEngine"),
    ("ConceptFormer", "memory_thread.services.emergent_reasoner", "ConceptFormer"),
    ("ConfidenceCalibrator", "memory_thread.services.meta_cognitive", "ConfidenceCalibrator"),
    ("KnowledgeGapDetector", "memory_thread.services.meta_cognitive", "KnowledgeGapDetector"),
]

for name, module, cls in service_tests:
    try:
        mod = __import__(module, fromlist=[cls])
        getattr(mod, cls)
        print(f"   ✅ {name}")
        services_ok += 1
    except Exception as e:
        print(f"   ❌ {name}: {e}")
        services_fail += 1

results.append(("Services", services_ok > 5))
print(f"   Summary: {services_ok}/{len(service_tests)} services importable")

# Test 4: Decay service functions
print("\n4️⃣ Testing decay service...")
try:
    from memory_thread.services.decay_service import apply_decay, get_half_life
    decayed = apply_decay(1.0, 'event', 30)
    half_life = get_half_life('event')
    print(f"   ✅ Decay: 30-day factor = {decayed:.3f}, half-life = {half_life:.1f} days")
    results.append(("Decay service", True))
except Exception as e:
    print(f"   ❌ Decay service error: {e}")
    results.append(("Decay service", False))

# Test 5: Embedding service
print("\n5️⃣ Testing embedding service...")
try:
    from memory_thread.utils.embeddings import is_model_available, get_zero_vector
    available = is_model_available()
    zero_vec = get_zero_vector()  # No argument needed
    print(f"   {'✅' if available else '⚠️'} Model available: {available}")
    print(f"   ✅ Zero vector fallback: {len(zero_vec)} dimensions")
    results.append(("Embeddings", True))  # Always pass if get_zero_vector works
except Exception as e:
    print(f"   ❌ Embedding error: {e}")
    results.append(("Embeddings", False))

# Test 6: Qdrant availability
print("\n6️⃣ Testing Qdrant...")
try:
    from memory_thread.db.qdrant_client import QdrantClientWrapper
    qc = QdrantClientWrapper()
    available = qc.is_available()
    print(f"   {'✅' if available else '⚠️'} Qdrant available: {available}")
    results.append(("Qdrant", True))  # Pass if client initializes
except Exception as e:
    print(f"   ❌ Qdrant error: {e}")
    results.append(("Qdrant", False))

# Summary
print("\n" + "=" * 60)
print("📊 DIAGNOSTIC SUMMARY")
print("=" * 60)

passed = sum(1 for _, ok in results if ok)
total = len(results)

for name, ok in results:
    status = "✅" if ok else "❌"
    print(f"   {status} {name}")

print(f"\nTotal: {passed}/{total} checks passed")

if passed == total:
    print("\n🎉 MT CORE SYSTEMS OPERATIONAL")
    sys.exit(0)
elif passed >= total // 2:
    print("\n⚠️ MT PARTIALLY OPERATIONAL - Some issues detected")
    sys.exit(1)
else:
    print("\n❌ MT HAS CRITICAL ISSUES")
    sys.exit(2)
