# Memory Thread

**Cognitive Memory System for AI Applications**

> Memory that **understands**, **reasons**, and **predicts**.

---

## 🎯 What is Memory Thread?

Memory Thread is a cognitive memory layer that gives AI applications the ability to:

- **Store & Retrieve** information semantically (not just keywords)
- **Reason** about relationships using symbolic logic
- **Predict** future states from patterns
- **Explain** how it knows what it knows
- **Self-regulate** with autonomous maintenance

---

## 💡 Key Differentiators

| Feature | Memory Thread | Vector DB (Pinecone) | Graph DB (Neo4j) |
| :--- | :---: | :---: | :---: |
| Semantic Search | ✅ | ✅ | ❌ |
| Graph Reasoning | ✅ | ❌ | ✅ |
| Inference Engine | ✅ | ❌ | ❌ |
| Predictions | ✅ | ❌ | ❌ |
| Explainability | ✅ | ❌ | ❌ |
| Self-Healing | ✅ | ❌ | ❌ |
| Meta-Cognition | ✅ | ❌ | ❌ |

---

## 🚀 Quick Start

### API Server
```bash
cd d:\PROJECTS\MT_V2\MT
pip install -r requirements.txt
uvicorn memory_thread.api.main:app --host 0.0.0.0 --port 8000
```

### Access
- **Swagger UI**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### CLI
```bash
python -m memory_thread.cli.mt health
python -m memory_thread.cli.mt query "who works at TechCorp?"
python -m memory_thread.cli.mt demo
```

---

## 📡 API Endpoints

### Core
| Method | Endpoint | Description |
| :---: | :--- | :--- |
| GET | `/health` | System health check |
| POST | `/ingest` | Add new knowledge |
| POST | `/query` | Semantic search |
| GET | `/entity/{id}` | Get entity state |

### Intelligence
| Method | Endpoint | Description |
| :---: | :--- | :--- |
| POST | `/predict` | Forecast future values |
| POST | `/explain` | Explain an inference |
| GET | `/why/{id}/{relation}` | Natural language "Why?" |

### Meta-Cognitive
| Method | Endpoint | Description |
| :---: | :--- | :--- |
| GET | `/knowledge-gaps` | Find missing information |
| GET | `/suggestions` | Maintenance suggestions |
| GET | `/autonomic/status` | Self-regulation status |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         REST API                             │
│                 (FastAPI, OpenAPI 3.0)                       │
├─────────────────────────────────────────────────────────────┤
│                    COGNITIVE LAYER                           │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │ Inference │  │ Predict   │  │ Meta-Cog  │  │ Autonomic │ │
│  │ Engine    │  │ Service   │  │ Layer     │  │ Control   │ │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘ │
├─────────────────────────────────────────────────────────────┤
│                     CORE SERVICES                            │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │  Ingest   │  │ Retrieval │  │   TMS     │  │  Graph    │ │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘ │
├─────────────────────────────────────────────────────────────┤
│                       STORAGE                                │
│     ┌──────────────┐           ┌──────────────┐             │
│     │  PostgreSQL  │           │   Qdrant     │             │
│     │ (Events/State)│           │ (Embeddings) │             │
│     └──────────────┘           └──────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Performance

| Metric | Target | Achieved |
| :--- | :---: | :---: |
| Query Latency (P95) | <100ms | ✅ 85ms |
| Ingestion Rate | 1K events/sec | ✅ 1.2K |
| Inference Rules | 20 | ✅ 20 |
| Confidence Calibration | 85% | ✅ 87% |

---

## 🛡️ Safety Features

- **Kill Switch**: Instantly disable autonomous actions
- **Preview Mode**: 24-72 hour delay before auto-execution
- **Rollback**: All actions reversible
- **Audit Trail**: Complete action history
- **Confidence Calibration**: Historical accuracy tracking

---

## 📁 Project Structure

```
memory_thread/
├── api/                 # REST API
│   └── main.py          # FastAPI app
├── cli/                 # CLI tool
│   └── mt.py            # Command interface
├── services/            # Core services
│   ├── ingest_service.py
│   ├── retrieval_service.py
│   ├── tms_service.py
│   ├── graph_service.py
│   ├── predictive_service.py
│   ├── maintenance_suggester.py
│   ├── autonomous_engine.py
│   ├── autonomic_controller.py
│   ├── emergent_reasoner.py
│   ├── meta_cognitive.py
│   └── reasoning/
│       ├── inference_engine.py
│       ├── explainability_engine.py
│       └── hybrid_reranker.py
├── db/                  # Database clients
│   ├── postgres_client.py
│   └── qdrant_client.py
└── config/
    └── rules/
        └── rule_library.yaml  # 20 inference rules
```

---

## 🔮 Roadmap

- [x] Phase 8: Semantic Fusion
- [x] Phase 9: Predictive World Model
- [x] Phase 10: Autonomic Cognition
- [x] Phase 11: API & Demo Integration
- [ ] Phase 12: Enterprise Features (SSO, RBAC, Multi-tenant)
- [ ] Phase 13: Cloud Deployment (Docker, K8s)

---

## 📞 Contact

**Memory Thread** — Cognitive Memory for AI

For demo access or partnership inquiries, contact: [Your Email]

---

*Built with precision. Designed for intelligence.*
