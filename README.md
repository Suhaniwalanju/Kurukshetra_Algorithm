# Verified Course Material Studio (Phase 1 of 3)

**Verified Course Material Studio** is an automated curriculum and slide generation studio tailored exclusively for professors who teach **CODING subjects**. It transforms programming concepts into minimal-text, beautifully branded PowerPoint presentations whose safe zones, collision avoidance, and typography are mathematically verified.

---

## Architecture & Tech Stack

- **Backend**: Python 3.11+ with **FastAPI**
- **Frontend**: **React 19** + **Vite** + **Tailwind CSS**
- **LLM**: Local **Ollama** (`qwen2.5:3b` / `phi3:latest`) with Pydantic JSON schema auto-retry
- **Presentation Engine**: **python-pptx** on blank 16:9 widescreen layout with **Pygments** syntax highlighting
- **Image & Slide Rendering**: LibreOffice headless / pdf2image + High-Fidelity PIL 1080p preview visualizer
- **Database**: SQLite via **SQLAlchemy**
- **Unit Testing**: **pytest** for layout engine and collision map

---

## Project Structure

```
Kurukshetra_dpu/
├── backend/
│   ├── main.py                 # FastAPI application routes & endpoints
│   ├── database.py             # SQLite database and DeckRecord model
│   ├── schemas.py              # Pydantic models for Deck, Slide, Config
│   ├── topic_validator.py      # Coding-only subject validator with friendly rejections
│   ├── template_registry.py    # Auto-detection of brand safe-zones & colors
│   ├── llm_generator.py        # Ollama integration with 3-attempt validation retry
│   ├── layout_engine.py        # Collision map, PIL text measurement & auto-split
│   ├── pptx_builder.py         # python-pptx builder with Pygments syntax highlighting
│   ├── slide_renderer.py       # High-res 1920x1080 slide renderer & automated checker
│   ├── diagram_renderer.py     # Mermaid and architectural diagram generator
│   ├── verifier_stub.py        # Clean CodeVerifier stub interface for Phase 2
│   ├── template_configs/       # Auto-detected human-editable JSON layout configs
│   └── tests/
│       └── test_layout_engine.py # Unit tests for layout engine
├── frontend/                   # React + Vite + Tailwind CSS UI
│   ├── src/
│   │   ├── components/
│   │   │   ├── Navbar.jsx
│   │   │   ├── DeckForm.jsx
│   │   │   ├── TemplatePreviewModal.jsx
│   │   │   ├── GenerationProgress.jsx
│   │   │   ├── SlideGallery.jsx
│   │   │   └── NonCodingErrorModal.jsx
│   │   ├── App.jsx
│   │   └── index.css
│   └── package.json
├── input/
│   └── templates/              # College templates (e.g. VIT Brand template)
├── output/                     # Generated .pptx decks and 1080p slide previews
└── README.md
```

---

## Setup & Running Guide

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Ollama running locally (`ollama serve`) with `qwen2.5:3b` or `phi3:latest`

### 2. Backend Setup
1. Open a terminal in the project root:
   ```bash
   pip install fastapi uvicorn python-pptx pdf2image pytest ollama pydantic sqlalchemy Pillow pygments
   ```
2. Start the FastAPI backend:
   ```bash
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   The backend API will run on `http://localhost:8000` (docs at `http://localhost:8000/docs`).

### 3. Frontend Setup
1. In a second terminal:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
2. Open your browser at `http://localhost:5173`.

---

## Running Unit Tests

Run the layout engine unit test suite using `pytest`:
```bash
python -m pytest backend/tests/test_layout_engine.py -v
```

The test suite validates:
1. **Coding Topic Validation**: Correctly accepts programming subjects and rejects non-coding subjects with informative messages.
2. **Word & Bullet Count Constraints**: Ensures no bullet exceeds 8 words and no slide exceeds 5 bullets.
3. **Element Collision Map**: Enforces a minimum 0.2 inch (29px) gutter between all elements.
4. **Safe-Zone Containment**: Ensures all text and code elements remain strictly inside configured zones.
5. **Presented By Placement**: Verifies placement on Cover & Closing slides in the bottom presented_by_zone.
6. **Automatic Splitting**: Verifies that overflowing slides are automatically split into continued slides.
7. **Java 21 Sample Deck**: End-to-end acceptance check with zero overlaps and zero overflow.

---

## Phase 1 Acceptance Criteria Checklist

- [x] **Template Registry**: Scans `/input/templates/` on startup. Auto-detects safe boundaries, margins, and brand colors into human-editable `/backend/template_configs/<college>.json`.
- [x] **Full-Slide Background**: Template PNG applied as full-slide background on every slide without stretching or cropping.
- [x] **Presented By Placement**: Appears in `presented_by_zone` at the bottom of Cover and Closing slides, and in small footer text on content slides.
- [x] **Automated Collision & Overflow Check**: Mathematical verification using PIL ImageFont measurements, 0.2" gutter, and auto-splitting. Zero overlaps on Java 21 sample deck.
- [x] **Word Count Restrictions**: Strict enforcement of maximum 5 bullets per slide and maximum 8 words per bullet.
- [x] **Downloadable PPTX**: Full presentation downloads as valid `.pptx` with Pygments syntax highlighting.
- [x] **Phase 2 Verifier Interface**: Clean `CodeVerifierStub` class ready for containerized code execution sandboxing in Phase 2.
