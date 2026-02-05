# Research Lineage Tracker

A React + FastAPI app to visualize research paper citation networks.

## Features

- **Pre-Order View**: Papers that the seed paper cited (references) - displayed as timeline by year
- **Post-Order View**: Papers that cite the seed paper - displayed as expandable tree
- Interactive graph visualization with Cytoscape.js
- Click-to-expand paper details
- Filter by year range and citation count

## Tech Stack

- **Frontend**: React + TypeScript, Vite, Cytoscape.js, Tailwind CSS
- **Backend**: FastAPI + Python

## Getting Started

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173` and proxies API requests to `http://localhost:8000`.

## API Endpoints

- `GET /api/paper/{paper_id}` - Get paper details
- `GET /api/paper/{paper_id}/references` - Get papers this paper cites
- `GET /api/paper/{paper_id}/citations` - Get papers citing this paper
