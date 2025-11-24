# Memory Thread Engine

**Memory Thread is a sophisticated, long-term cognitive memory subsystem designed for advanced AI agents. It provides a robust framework for ingesting, structuring, and retrieving information, mimicking a more human-like memory process.**

## Core Concepts

The engine is built on a hybrid data model that combines the strengths of two distinct database technologies:

1.  **Vector Database (Qdrant):** Used for **semantic search**. Every memory is converted into a high-dimensional vector embedding. This allows the system to find memories based on their meaning and context, not just keywords.
2.  **Graph Database (PostgreSQL):** Used as a **graph overlay and metadata store**. It serves as the source of truth for all memory objects and, more importantly, it maps the relationships between memories. This allows the system to traverse connections, understand causality, and refine search results based on a memory's relationships.

## Architecture & Workflow

The system is composed of two primary workflows: the **Ingestion Pipeline** and the **Retrieval Algorithm**.

### 1. Ingestion Pipeline

When new information is presented to the system, it passes through a multi-step pipeline:

1.  **Classification:** The raw text is first classified to determine its fundamental type (e.g., `identity`, `preference`, `event`) and to detect negation. This is done using a set of precise linguistic rules.
2.  **Extraction:** The system then extracts structured data from the text. This is a 3-step process involving:
    *   **NER (Named Entity Recognition):** Using `spaCy` to identify entities like people, places, and dates.
    *   **LLM Extraction:** Using a placeholder for a Large Language Model to extract deeper insights like topics, emotions, and deadlines.
    *   **Filtering:** Merging the results and keeping only the most critical fields.
3.  **Object Creation:** The processed data is used to construct a `MemoryObject`, a standardized Pydantic model that enforces data integrity.
4.  **Embedding Generation:** The original text content is passed to an embedding model (placeholder) to generate a `1536-dimension` vector.
5.  **Dual Storage:** The memory is stored in both databases:
    *   The full `MemoryObject` (excluding the transient embedding) is saved in the **PostgreSQL** `memories` table.
    *   The vector embedding and a lightweight payload are upserted into the **Qdrant** collection.
6.  **Graph Construction:** The system (in a future phase) will create edges in the `memory_edges` table, linking the new memory to existing, related memories.

### 2. Retrieval Algorithm

When a query is made to retrieve memories, the system uses a 3-step hybrid algorithm:

1.  **Vector Search (Candidate Generation):** The query is first converted into an embedding. This embedding is used to perform a semantic search in **Qdrant**, retrieving the **top 40** most similar memories. These are the initial candidates.
2.  **Graph Refinement & Scoring:** Each of the 40 candidates is then enriched and re-scored:
    *   The system fetches the candidate's neighbors from the **PostgreSQL** graph.
    *   A final score is calculated using a weighted formula that considers:
        *   `0.6 * vector_similarity`: The initial score from Qdrant.
        *   `0.2 * edge_weight`: The strength of its connections to other memories.
        *   `0.1 * importance`: The intrinsic importance of the memory.
        *   `0.1 * recency_decay`: A score that decays the older a memory gets.
3.  **Final Ranking:** The memories are sorted by this new hybrid score, and the **top 10** are returned to the user.

## Technology Stack

| Component             | Technology / Library                                       | Purpose                                                 |
| --------------------- | ---------------------------------------------------------- | ------------------------------------------------------- |
| **Backend Framework** | [FastAPI](https://fastapi.tiangolo.com/)                   | For building the high-performance API.                  |
| **Vector Database**   | [Qdrant](https://qdrant.tech/)                             | For storing vector embeddings and semantic search.      |
| **Graph Database**    | [PostgreSQL](https://www.postgresql.org/)                  | For storing memory metadata and graph relationships.    |
| **Data Validation**   | [Pydantic](https://docs.pydantic.dev/)                     | For strict data modeling and validation.                |
| **NLP**               | [spaCy](https://spacy.io/)                                 | For Named Entity Recognition (NER).                     |
| **Database Drivers**  | `psycopg2-binary`, `qdrant-client`                         | For connecting to Postgres and Qdrant.                  |
| **LLM Interface**     | `LLMProvider` (Abstract Class)                             | A placeholder to allow for any LLM backend.             |

## Project Structure

```
/memory_thread
├── /api            # FastAPI application and routes
├── /config         # Application settings and configuration
├── /db             # Database schemas and client connection logic
├── /models         # Pydantic data models (e.g., MemoryObject)
├── /services       # Core business logic for each module (ingestion, retrieval, etc.)
├── /utils          # Helper utilities (embeddings, NER, logging)
└── /workers        # Background workers for maintenance tasks (decay, eviction)
/tests              # Unit and integration tests
README.md
```

## Setup & Installation

1.  **Environment Variables:**
    Create a `.env` file in the root directory (this is excluded by `.gitignore`). The application uses environment variables for database configuration. The default values are in `memory_thread/config/settings.py`.

    ```sh
    # Example .env file
    POSTGRES_USER=myuser
    POSTGRES_PASSWORD=mypassword
    POSTGRES_SERVER=localhost
    POSTGRES_DB=memory_thread_db
    QDRANT_HOST=localhost
    ```

2.  **Dependencies:**
    Install the required Python packages. It is recommended to use a virtual environment.

    ```sh
    pip install -r requirements.txt
    # Note: A requirements.txt file will be added in a future phase.
    # For now, install manually:
    pip install fastapi uvicorn pydantic psycopg2-binary qdrant-client spacy
    ```

3.  **NLP Model:**
    Download the required `spaCy` model.

    ```sh
    python -m spacy download en_core_web_sm
    ```

## Running the Application

Once the setup is complete, you can start the FastAPI server using `uvicorn`.

```sh
uvicorn memory_thread.api.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.
```
