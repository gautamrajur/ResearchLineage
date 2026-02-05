# ResearchLineage

## Project Overview
A React + FastAPI app to visualize research paper citation networks. Users enter a "seed" research paper and can view:
- **Pre-Order View**: Papers that the seed paper cited (references) - displayed as timeline by year
- **Post-Order View**: Papers that cite the seed paper - displayed as expandable tree

## Tech Stack
- **Frontend**: React + TypeScript, Vite, Cytoscape.js (via react-cytoscapejs), Tailwind CSS
- **Backend**: FastAPI + Python
- **Data**: Mock data (Semantic Scholar API integration planned)

## Project Structure
```
ResearchLineage/
├── frontend/           # React + Vite app
│   ├── src/
│   │   ├── components/ # React components
│   │   ├── api/        # API client
│   │   └── types/      # TypeScript types
│   └── package.json
├── backend/            # FastAPI server
│   ├── main.py         # API endpoints
│   └── mock_data.py    # Mock paper data
├── CLAUDE.md
└── README.md
```

## Development Setup
```bash
# Backend
cd backend
pip install fastapi uvicorn
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Key Commands
- Backend: `uvicorn main:app --reload --port 8000`
- Frontend: `npm run dev`

## API Endpoints
- `GET /api/paper/{paper_id}` - Get paper details
- `GET /api/paper/{paper_id}/references` - Get papers this paper cites
- `GET /api/paper/{paper_id}/citations` - Get papers citing this paper

## Performance Rules
1. Limit to 50 nodes max
2. Use straight edges (faster than bezier)
3. Hide labels when zoomed out (zoom < 0.7)
4. Use cy.batch() for multiple updates
