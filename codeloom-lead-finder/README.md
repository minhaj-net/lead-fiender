# Codeloom Lead Finder — Part 1

A **local** lead-research automation system for Codeloom.
Processes publicly accessible business information, qualifies businesses
that appear to have no website, identifies publicly provided business
contact information, stores qualified leads, and exports them to CSV.

---

## Architecture

```
Chrome Extension (Manifest V3)
         ↓
Local FastAPI Backend (Python)
         ↓  ↓  ↓
Playwright  OpenAI  MySQL
                        ↓
                       CSV
```

---

## Quick Start

### 1. Prerequisites

Install the following on your PC:
- Python 3.11+
- Google Chrome
- MySQL Server 8+
- Git (optional but recommended)

### 2. Clone / Open project

```bash
cd codeloom-lead-finder
```

### 3. Create and activate virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python -m venv venv
source venv/bin/activate
```

### 4. Install Python packages

```bash
pip install -r requirements.txt
```

### 5. Install Playwright browsers

```bash
playwright install chromium
```

### 6. Configure environment

```bash
cp .env.example .env
# Edit .env with your MySQL password and OpenAI API key
```

### 7. Set up MySQL database

Log into MySQL and run:

```sql
CREATE DATABASE codeloom_leads CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

The backend will auto-create all tables on first startup.

### 8. Start the backend

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Visit http://127.0.0.1:8000/docs to see the interactive API docs.

### 9. Load the Chrome Extension

1. Open Chrome → go to `chrome://extensions/`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the `extension/` folder inside this project
5. The Codeloom icon will appear in your toolbar

### 10. Start automation

Click the Codeloom extension icon → click **START AUTOMATION**.

---

## Project Structure

```
codeloom-lead-finder/
├── backend/
│   ├── main.py                   # FastAPI app entry point
│   ├── config.py                 # Settings from .env
│   ├── database.py               # MySQL connection
│   ├── models.py                 # DB table definitions
│   ├── schemas.py                # Pydantic request/response models
│   ├── routers/
│   │   ├── health.py             # GET /health
│   │   ├── automation.py         # POST /automation/start|stop
│   │   └── leads.py              # GET /leads, GET /leads/export
│   ├── services/
│   │   ├── automation.py         # Playwright orchestration
│   │   ├── lead_discovery.py     # Extract leads from public sources
│   │   ├── business_identifier.py# Rule-based + AI business classification
│   │   ├── website_detector.py   # Website YES/NO/UNCERTAIN
│   │   ├── contact_detector.py   # Public business contact extraction
│   │   ├── duplicate_checker.py  # Prevent duplicate records
│   │   ├── lead_scorer.py        # Rule-based + AI lead scoring
│   │   ├── csv_exporter.py       # Pandas CSV export
│   │   └── ai_service.py         # OpenAI API wrapper
│   └── utils/
│       ├── logger.py             # Structured logging
│       └── normalizers.py        # URL / phone normalization
├── extension/
│   ├── manifest.json
│   ├── popup.html
│   ├── popup.js
│   ├── background.js
│   ├── content.js
│   └── style.css
├── data/                         # CSV exports saved here
├── tests/                        # Pytest unit tests
├── .env.example                  # Copy to .env and fill in secrets
├── .gitignore
├── requirements.txt
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Backend health check |
| POST | `/automation/start` | Start Playwright automation |
| POST | `/automation/stop` | Stop running automation |
| GET | `/automation/status` | Current automation status |
| GET | `/leads` | List all qualified leads |
| GET | `/leads/export` | Export leads to CSV |
| DELETE | `/leads/{id}` | Delete a lead |

---

## Lead Priority Levels

| Score | Priority |
|-------|----------|
| 90–100 | 🔥 HOT |
| 70–89 | ✅ GOOD |
| 50–69 | 🟡 MEDIUM |
| 0–49 | ⬇️ LOW |

---

## Security Notes

- The OpenAI API key is stored only in `.env` — never in source code or the extension
- The backend only listens on `127.0.0.1` (localhost) during MVP
- No personal/hidden information is collected — only publicly provided business info
- `.env` is in `.gitignore` and must never be committed

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Part 2 (Future)

Part 2 will add WhatsApp outreach, personalized messaging, and response tracking.
Do not start Part 2 until Part 1 is stable and tested.
