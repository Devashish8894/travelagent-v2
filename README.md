# TravelAgent AI Engine 🌍✈️

Autonomous Multi-Modal Travel Itinerary & Dynamic Budget Orchestrator powered by FastAPI, LangGraph, Google Gemini, and SerpApi.

---

## 🌟 Key Capabilities

* **Multi-Modal Route Planning:** Dynamically orchestrates flights (Google Flights via SerpApi), hotels (Google Hotels), intercity transit (IRCTC trains, bus operators), and local cabs.
* **Deterministic Budget Guardrails:** Locks downstream reservations and provides shortfall warnings when aggregated costs surpass user budgets.
* **Automated KYC / Passport OCR:** Enforces border compliance checks on international itineraries using Gemini Vision OCR extraction.
* **Persistent Vector & Relational Storage:** ChromaDB for context embeddings and SQLite for tracking trip histories.
* **Modern Reactive Interface:** React + Vite frontend with dynamic tabs, markdown rendering, and real-time state synchronization.

---

## 🛠️ Architecture Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 18, Vite, Tailwind CSS, Lucide Icons, React-Markdown |
| **Backend** | FastAPI, Uvicorn, Pydantic v2 |
| **Agent Core** | LangGraph, LangChain, Google Gemini Flash |
| **External Tools** | SerpApi (Google Flights & Hotels), Local Transit Engines |
| **Databases** | ChromaDB (Vector Store), SQLite (`chat_history.db`) |
| **Containerization** | Docker, Docker Compose |

---

## 📂 Project Structure

```text
travelagent-v2/
├── app/
│   ├── agents/          # LangGraph state machine, nodes, and graph definition
│   ├── db/              # ChromaDB vector store and SQLite history operations
│   ├── services/        # Passport OCR (Gemini Vision) and media utilities
│   ├── tools/           # SerpApi flights, hotels, transit, and weather tools
│   └── main.py          # FastAPI application routes and endpoints
├── frontend/
│   ├── public/          # Static assets (logo, favicon)
│   ├── src/             # React application (TravelPlanner.jsx, components)
│   ├── Dockerfile       # Container definition for frontend
│   └── package.json
├── chat_history.db      # SQLite query history database
├── chroma_db/           # ChromaDB persistent vector storage
├── docker-compose.yml   # Multi-container orchestration (Backend + Frontend)
├── Dockerfile           # Backend production container configuration
├── requirements.txt     # Python backend dependencies
└── README.md
