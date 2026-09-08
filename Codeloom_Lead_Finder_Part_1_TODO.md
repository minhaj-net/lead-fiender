# Codeloom Lead Finder — Part 1
## Local Chrome Extension + Python Backend + MySQL + OpenAI

> **Goal:** Build a local lead-research automation system for Codeloom that processes permitted/publicly accessible business information, qualifies businesses that appear to have no website, identifies publicly provided business contact information, stores qualified leads, and exports them to CSV.

---

## 1. Final Architecture

```text
                    ┌──────────────────────┐
                    │   Google Chrome      │
                    │                      │
                    │ Codeloom Extension   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Local Backend      │
                    │ Python + FastAPI     │
                    └──────────┬───────────┘
                               │
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
          ┌────────────┐ ┌────────────┐ ┌────────────┐
          │ Playwright │ │  OpenAI    │ │   MySQL    │
          │ Automation │ │    API     │ │  Database  │
          └────────────┘ └────────────┘ └────────────┘
                               │
                               ▼
                         ┌───────────┐
                         │   CSV     │
                         └───────────┘
```

### Main components

- **Chrome Extension:** User interface and browser-side control.
- **Python:** Main application/automation logic.
- **FastAPI:** Local backend/API layer.
- **Playwright:** Browser automation.
- **MySQL:** Persistent lead database and duplicate checking.
- **OpenAI API:** Business classification, category detection, ambiguous-case analysis, and lead scoring.
- **Pandas:** Data processing and CSV export.
- **Chrome/Chromium:** Browser runtime for Playwright.

### Not required for the first version

- Meta Graph API
- Search API
- VPS/Cloud server
- Public Chrome Web Store publication
- Separate frontend website/dashboard

---

# 2. Important Scope

The system should work with **permitted/publicly accessible business information**.

Do not design the system to:

- access private/hidden profile information;
- bypass login, privacy controls, CAPTCHAs, rate limits, or other access restrictions;
- collect personal/hidden phone or WhatsApp numbers;
- perform unrestricted scraping against platform restrictions.

The target is **business lead research**, not private-person data harvesting.

---

# 3. Phase 0 — Requirements & Rules

- [ ] Define target business categories.
- [ ] Define target countries/markets.
- [ ] Define which Facebook sources are permitted for the workflow.
- [ ] Define the exact public fields to collect.
- [ ] Define what counts as `Website = YES`.
- [ ] Define what counts as `Website = NO`.
- [ ] Define when a website result is `UNCERTAIN`.
- [ ] Define what counts as a public business contact.
- [ ] Define minimum lead-quality requirements.
- [ ] Define CSV columns.
- [ ] Define duplicate rules.

---

# 4. Phase 1 — Development Environment

## Install

- [ ] Python 3
- [ ] Google Chrome
- [ ] VS Code
- [ ] MySQL Server
- [ ] Git (recommended)
- [ ] Create project folder

Recommended project:

```text
codeloom-lead-finder/
├── backend/
├── extension/
├── data/
├── tests/
├── .env
├── .gitignore
└── README.md
```

---

# 5. Phase 2 — Python Backend

## Create Python environment

- [ ] Create virtual environment.
- [ ] Activate virtual environment.
- [ ] Create `requirements.txt`.

Initial packages:

```text
fastapi
uvicorn
playwright
pandas
mysql-connector-python
python-dotenv
openai
```

## Backend tasks

- [ ] Create FastAPI application.
- [ ] Create health-check endpoint.
- [ ] Create start-automation endpoint.
- [ ] Create stop-automation endpoint.
- [ ] Create lead-save endpoint/service.
- [ ] Create CSV-export endpoint/service.
- [ ] Add environment-variable configuration.
- [ ] Add logging.
- [ ] Add error handling.

---

# 6. Phase 3 — Chrome Extension

## Extension files

```text
extension/
├── manifest.json
├── popup.html
├── popup.js
├── content.js
├── background.js
└── style.css
```

## Tasks

- [ ] Create Manifest V3 extension.
- [ ] Create popup UI.
- [ ] Add `START` button.
- [ ] Add `STOP` button.
- [ ] Add status display.
- [ ] Connect extension to local FastAPI backend.
- [ ] Show automation status.
- [ ] Handle backend connection errors.
- [ ] Load extension as unpacked extension.
- [ ] Test locally in Chrome.

### No Chrome Web Store required

For personal/local use, the first version can remain an **unpacked extension in Developer Mode**.

---

# 7. Phase 4 — Extension ↔ Backend Connection

First build a simple test before touching Facebook automation.

Expected flow:

```text
Chrome Extension
      ↓
Click START
      ↓
POST request
      ↓
FastAPI
      ↓
"Automation started"
      ↓
Extension displays status
```

Checklist:

- [ ] Extension can reach localhost.
- [ ] FastAPI receives request.
- [ ] Backend returns JSON.
- [ ] Extension displays response.
- [ ] START works.
- [ ] STOP works.
- [ ] Error handling works.

Only continue after this test is stable.

---

# 8. Phase 5 — Playwright Browser Automation

## Setup

- [ ] Install Playwright.
- [ ] Install required browser runtime.
- [ ] Create browser launch module.
- [ ] Create page/navigation module.
- [ ] Create safe wait/retry logic.
- [ ] Create logging.
- [ ] Avoid bypassing CAPTCHAs or access controls.

## Automation objective

The automation should assist with the same permitted/public research workflow that a user can perform normally, without attempting to access restricted information.

---

# 9. Phase 6 — Lead Discovery

Define how leads enter the system.

Example:

```text
Selected Group/Source
        ↓
Relevant business post
        ↓
Business/Page/Profile reference
        ↓
Lead candidate
```

Tasks:

- [ ] Define source configuration.
- [ ] Identify relevant business posts/content.
- [ ] Extract available public business information.
- [ ] Normalize names and URLs.
- [ ] Store raw/initial lead record.
- [ ] Add source information.

---

# 10. Phase 7 — Business Identification

Use Python rules first.

Possible signals:

- Business-related description
- Business category
- Product/service language
- Contact/order language
- Business Page indicators

Then optionally use OpenAI for ambiguous cases.

Example output:

```json
{
  "is_business": true,
  "category": "Restaurant",
  "confidence": 0.94
}
```

Checklist:

- [ ] Define business categories.
- [ ] Create rule-based filtering.
- [ ] Create AI classification for ambiguous cases.
- [ ] Store classification result.
- [ ] Store confidence/decision reason where useful.

---

# 11. Phase 8 — Website Detection

### Primary source

Check the available public Facebook business information first.

Possible result:

```text
YES
NO
UNCERTAIN
```

### Important

`NO` means the system did not find a website in the permitted/public information it checked. It should not claim with 100% certainty that the business has no website anywhere on the internet.

Tasks:

- [ ] Detect website/link fields.
- [ ] Normalize website URLs.
- [ ] Validate obvious website links.
- [ ] Mark `YES`.
- [ ] Mark `NO` when no website is present in the checked public information.
- [ ] Mark ambiguous cases as `UNCERTAIN`.
- [ ] Exclude `YES` leads from the target list.
- [ ] Optionally send `UNCERTAIN` cases to AI/manual review.

---

# 12. Phase 9 — Public Business Contact Detection

Only process contact information that is publicly provided as business contact information and is within the permitted workflow.

Possible fields:

```text
business_phone
business_whatsapp
business_email
```

Tasks:

- [ ] Detect public business phone.
- [ ] Detect public business WhatsApp.
- [ ] Normalize phone numbers.
- [ ] Validate obvious number formats.
- [ ] Avoid hidden/private information.
- [ ] Store source/context for the contact where appropriate.

---

# 13. Phase 10 — OpenAI Integration

## OpenAI's role

AI is **not** the main browser automation engine.

Use OpenAI when the system needs interpretation.

Possible tasks:

### Business classification

```text
Input:
Public business description/post

Output:
Business / Not business
Category
Confidence
```

### Lead scoring

Example signals:

- No website found in checked public information
- Public business contact available
- Active business presence
- Clear products/services
- Good fit for web-development outreach

Example:

```json
{
  "score": 91,
  "priority": "HOT"
}
```

### Ambiguous cases

If rules cannot confidently determine something, send only the necessary public text/data to the AI and receive a structured decision.

Checklist:

- [ ] Create OpenAI API key.
- [ ] Store key in `.env`.
- [ ] Never hard-code API key.
- [ ] Create AI service module.
- [ ] Use structured JSON output.
- [ ] Add error handling.
- [ ] Add usage/cost monitoring.
- [ ] Avoid sending unnecessary personal information.

---

# 14. Phase 11 — MySQL Database

Recommended database:

```text
codeloom_leads
```

Possible tables:

```text
leads
sources
automation_runs
```

## `leads` example fields

```text
id
business_name
category
facebook_url
page_url
country
city
website
website_status
business_phone
business_whatsapp
source
source_post
lead_score
lead_priority
status
created_at
updated_at
```

### Database tasks

- [ ] Create MySQL database.
- [ ] Create tables.
- [ ] Connect FastAPI/Python to MySQL.
- [ ] Insert lead.
- [ ] Update lead.
- [ ] Query leads.
- [ ] Detect duplicates.
- [ ] Add indexes.
- [ ] Handle database errors.

---

# 15. Phase 12 — Duplicate Detection

Before inserting a lead:

```text
New lead
   ↓
Check existing database
   ↓
Same business/contact/page?
   ├── YES → Update/Skip
   └── NO  → Insert
```

Possible duplicate keys:

- Facebook Page URL
- normalized business/contact combination
- other stable public business identifiers

Tasks:

- [ ] Define unique-key strategy.
- [ ] Normalize URLs.
- [ ] Normalize phone numbers.
- [ ] Check before insert.
- [ ] Prevent duplicate records.

---

# 16. Phase 13 — Lead Scoring

Example:

```text
90–100 → HOT
70–89  → GOOD
50–69  → MEDIUM
0–49   → LOW
```

Possible scoring logic:

```text
No website found        → positive
Public business contact → positive
Clear business           → positive
Active presence          → positive
Good web-service fit     → positive
Uncertain data           → negative
```

The exact scoring formula should be decided after testing real leads.

Tasks:

- [ ] Define scoring rules.
- [ ] Test on sample leads.
- [ ] Compare AI score vs rule-based score.
- [ ] Adjust weights.
- [ ] Store final score.

---

# 17. Phase 14 — CSV Export

Use Pandas.

Example output:

```text
Codeloom_Leads_YYYY-MM-DD.csv
```

Recommended columns:

```text
Business Name
Category
Facebook URL
Page URL
Country
City
Website
Website Status
Business Phone
Business WhatsApp
Source
Source Post
Lead Score
Priority
Status
```

Tasks:

- [ ] Create CSV export function.
- [ ] Filter qualified leads.
- [ ] Sort by lead score.
- [ ] Export CSV.
- [ ] Test CSV encoding.
- [ ] Add date to filename.

---

# 18. Phase 15 — Chrome Extension UI

Keep the first UI simple.

Example:

```text
┌──────────────────────────────┐
│     Codeloom Lead Finder     │
│                              │
│ Status: Ready                │
│                              │
│ Sources:  5                  │
│ Leads:    0                  │
│                              │
│ [ START AUTOMATION ]         │
│ [ STOP ]                     │
│                              │
│ Website: 0                   │
│ No Website: 0                │
│ Qualified: 0                 │
└──────────────────────────────┘
```

Tasks:

- [ ] Start button.
- [ ] Stop button.
- [ ] Status.
- [ ] Lead counter.
- [ ] Qualified counter.
- [ ] Error display.
- [ ] CSV export button.

---

# 19. Phase 16 — Testing

Do not immediately run it against a large workload.

Start small.

```text
Test 1 → 1 lead
Test 2 → 5 leads
Test 3 → 20 leads
Test 4 → 50 leads
```

For every lead verify:

- [ ] Correct business name
- [ ] Correct Facebook URL
- [ ] Correct category
- [ ] Correct website status
- [ ] Contact data is public business information
- [ ] No duplicate
- [ ] Correct AI classification
- [ ] Correct lead score
- [ ] Correct MySQL record
- [ ] Correct CSV record

---

# 20. Error Handling

The system should not crash because one lead fails.

Possible states:

```text
SUCCESS
SKIPPED
DUPLICATE
UNCERTAIN
FAILED
```

Tasks:

- [ ] Add try/except handling.
- [ ] Log failed leads.
- [ ] Continue processing after individual failures.
- [ ] Add retry only where appropriate.
- [ ] Save progress periodically.
- [ ] Make START/STOP reliable.

---

# 21. Security

- [ ] Keep OpenAI API key in `.env`.
- [ ] Add `.env` to `.gitignore`.
- [ ] Do not put API keys in Chrome Extension source code.
- [ ] Keep local backend restricted to localhost during MVP.
- [ ] Do not store unnecessary personal information.
- [ ] Do not bypass Facebook security/privacy controls.

---

# 22. Final MVP Definition

The first complete version is considered done when:

```text
Chrome Extension
       ↓
START
       ↓
Local FastAPI Backend
       ↓
Process permitted/public business information
       ↓
Identify business
       ↓
Check website information
       ↓
Identify public business contact
       ↓
Save qualified lead
       ↓
MySQL
       ↓
OpenAI classification/scoring
       ↓
CSV
```

And the user can run the whole process **locally on their own PC** without:

- Meta API
- Search API
- VPS
- Chrome Web Store publication

---

# 23. Recommended Build Order

Follow this exact order:

- [ ] **1. Install Python + VS Code + MySQL + Chrome**
- [ ] **2. Create project folder**
- [ ] **3. Create Python virtual environment**
- [ ] **4. Install Python packages**
- [ ] **5. Create FastAPI backend**
- [ ] **6. Test backend**
- [ ] **7. Create Chrome Extension**
- [ ] **8. Load unpacked extension**
- [ ] **9. Connect Extension → FastAPI**
- [ ] **10. Test START/STOP**
- [ ] **11. Add Playwright**
- [ ] **12. Build small lead-discovery module**
- [ ] **13. Add business identification**
- [ ] **14. Add website detection**
- [ ] **15. Add public business contact detection**
- [ ] **16. Add MySQL**
- [ ] **17. Add duplicate detection**
- [ ] **18. Add OpenAI**
- [ ] **19. Add lead scoring**
- [ ] **20. Add CSV export**
- [ ] **21. Add UI statistics**
- [ ] **22. Test with small batches**
- [ ] **23. Fix errors**
- [ ] **24. Finalize Part 1 MVP**

---

# 24. Part 1 → Part 2 Boundary

**Part 1 ends here:**

```text
Lead Discovery
      ↓
Qualification
      ↓
Database
      ↓
CSV
```

**Part 2 will start from:**

```text
Qualified Leads / CSV
      ↓
WhatsApp Outreach
      ↓
Personalized Message
      ↓
Send/Approval
      ↓
Follow-up
      ↓
Response Tracking
```

Do not build Part 2 until Part 1 is stable.

---

# 25. First Task — Start Here

For now, ignore everything after Phase 1.

### Immediate TODO

- [ ] Install Python
- [ ] Install VS Code
- [ ] Install MySQL
- [ ] Confirm Google Chrome is installed
- [ ] Create `codeloom-lead-finder` folder
- [ ] Open it in VS Code
- [ ] Create `backend` and `extension` folders

Once this is complete, move to **Phase 2: Python + FastAPI setup**.

---

## Final Tech Stack

```text
Chrome
   +
Chrome Extension (Manifest V3)
   +
Python
   +
FastAPI
   +
Playwright
   +
MySQL
   +
OpenAI API
   +
Pandas
   =
Codeloom Lead Finder — Part 1
```
