# FaqSmartBuddy - ADK Service with Multiple Useful Tools

An ADK service with multiple useful tools built on Google's Agent Development Kit (ADK) and Gemini AI, deployed on Google Cloud Run. It hosts two independent assistants — **FaqAssistant** and **RepoWeightBuddy** — both accessible from a single `adk web` session.

## 🎯 Overview

FaqSmartBuddy is an ADK service with multiple useful tools:

- **FaqAssistant** — AI-powered customer support agent that answers questions about SmartBudget products. Uses Firestore for product catalog and conversation history.
- **RepoWeightBuddy** — DevOps assistant that estimates the total on-disk footprint of any GitHub repository after installation, using static analysis, script scanning, and optional web verification.

## ✨ Features

### FaqAssistant
- **Smart Product Search** - Matches user queries to relevant products using keyword analysis
- **Conversation History** - Maintains context across multiple interactions
- **Purchase Tracking** - Retrieves and displays customer purchase history
- **Real-time Responses** - Powered by Gemini 2.5 Flash model
- **Cloud-Native** - Deployed on Google Cloud Run with auto-scaling

### RepoWeightBuddy
- **GitHub Static Analyzer** - Fetches repo file tree and parses dependency files (`requirements.txt`, `package.json`, `environment.yml`)
- **Script Parser** - Scans shell scripts, Makefiles, and READMEs for hidden downloads (models, datasets, system packages)
- **Web Verification** - Uses Browser Use API to find explicit hardware/storage requirements in docs when confidence is low
- **Structured Report** - Outputs estimated size range, breakdown by category, and confidence score

## 🏗️ Architecture

```
User Request → Cloud Run (FastAPI) → ADK Agent → Gemini AI
                                    ↓
                              Firestore DB
                        (Products & Conversations)

adk web .
  ├── FaqAssistant      (customer support)
  └── RepoWeightBuddy   (repo size estimator)
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud account (FaqAssistant only)
- Firebase project with Firestore enabled (FaqAssistant only) - firebase.json in root folder (NEED TO INPUT!!!)
- Gemini API key (both agents)

### Local Development

1. **Clone and setup**
   ```bash
   cd FaqSmartBuddy
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment**

   Edit `.env` in the root directory:
   ```env
   GOOGLE_API_KEY=your_gemini_api_key
   GOOGLE_GENAI_USE_VERTEXAI=0

   # RepoWeightBuddy (both optional)
   GITHUB_TOKEN=your_github_token        # avoids GitHub API rate limits and access repositories (CRUCIAL)
   BROWSER_USE_API_KEY=your_key          # enables web verification step
   ```


## 🔐 How to Create a GitHub Personal Access Token (PAT)

You don't "find" an existing token — you must generate a new one.

As of 2026, GitHub offers two types of tokens. For most use cases (like an ADK agent), the **Classic token** is the easiest to set up.

---

### 📍 Steps to Generate a Token

2.1 **Go to Settings**
   - Click your profile picture (top-right corner)
   - Select **Settings**

2.2 **Open Developer Settings**
   - Scroll to the bottom of the left sidebar
   - Click **Developer settings**

2.3 **Navigate to Personal Access Tokens**
   - Click **Personal access tokens**
   - Then select **Tokens (classic)**

2.4 **Generate New Token**
   - Click **Generate new token**
   - Choose **"classic"** if prompted

2.5 **Configure Token**
   - Give it a name, e.g.:
     ```
     ADK-Repo-Weight-Agent
     ```
   - Set an expiration (recommended for security)

2.6 **Select Scopes**
   - Check:
     ```
     repo
     ```
   - This allows access to repositories and their file trees

2.7 **Generate and Save**
   - Click **Generate token**

---

### ⚠️ Important

> Copy the token immediately (it starts with `ghp_...`).  
> GitHub will **never show it again** after you leave the page.

Store it securely (e.g., in a `.env` file):
```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxx



3. **Add Firebase credentials** (FaqAssistant only)

   Place your `firebase_key.json` in the root directory.

4. **Seed product data** (FaqAssistant only, optional)
   ```bash
   python FaqAssistant/seed_products.py
   ```

5. **Run both agents together**
   ```bash
   adk web .
   ```
   Open `http://localhost:8000`, then select an agent from the dropdown:
   - **FaqAssistant** — ask product and support questions
   - **RepoWeightBuddy** — paste a GitHub URL to estimate install size

   To run a single agent in the terminal (no UI):
   ```bash
   adk run FaqAssistant
   # or
   adk run RepoWeightBuddy
   ```

---

## 💬 Using FaqAssistant

FaqAssistant answers questions about SmartBudget products and handles purchase lookups.

**Example prompts:**
- `What products do you have?`
- `Tell me about SmartBudget Pro`
- `Have I purchased SmartBudget Family?`
- `Which plan is best for a student?`

**Required:** Firebase credentials (`firebase_key.json`) and a Firestore database seeded with product data.

---

## ⚖️ Using RepoWeightBuddy

RepoWeightBuddy estimates how much disk space a GitHub repository will consume after installation.

**Example prompts:**
- `Identify the weight of this repo https://github.com/owner/repo`
- `How much disk space will https://github.com/owner/repo.git need?`
- `Estimate the install size of https://github.com/owner/repo`

**What it does:**
1. Fetches the full file tree via GitHub API
2. Parses `requirements.txt`, `package.json`, `environment.yml` for dependency sizes
3. Scans shell scripts and README for hidden downloads (models, datasets, apt packages)
4. If confidence is below 70%, uses Browser Use to verify requirements in external docs
5. Returns a size range, breakdown, and confidence score

**Output format:**
1. Repo size range (e.g. `1.2 GB - 1.8 GB`)
2. Files and lines that explain large sizes
3. Brief description of what the project does

**Optional env vars for better results:**
- `GITHUB_TOKEN` — prevents rate limiting on large or private repos
- `BROWSER_USE_API_KEY` — enables the web verification step

## ☁️ Cloud Deployment

### Option 1: Automated Script

```bash
bash deploy.sh
```

### Option 2: Manual Deployment

```bash
gcloud run deploy faqsmartbuddy-agent \
  --source . \
  --platform managed \
  --region us-central1 \
  --project your-project-id \
  --set-env-vars "GOOGLE_API_KEY=your_key,GOOGLE_PROJECT_ID=your_project,GOOGLE_GENAI_USE_VERTEXAI=0" \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --allow-unauthenticated
```

## 📡 API Usage

### Health Check
```bash
curl https://your-service-url.run.app/health
```

### Send Message
```bash
curl -X POST https://your-service-url.run.app/run \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "FaqAssistant",
    "new_message": "What products do you have?"
  }'
```

### Response Format
```json
[
  {
    "type": "agent_response",
    "content": "We have SmartBudget Pro, SmartBudget Basic, SmartBudget Family, SmartBudget Business, and SmartBudget Student."
  }
]
```

## 📁 Project Structure

```
FaqSmartBuddy/
├── FaqAssistant/
│   ├── agent.py              # FAQ agent logic + Firestore callbacks
│   ├── firebase_db.py        # Firestore connection
│   ├── seed_products.py      # Product data seeder
│   └── __init__.py
├── RepoWeightBuddy/
│   ├── agent.py              # RepoWeight agent + 3 tools
│   └── __init__.py
├── .env                      # Shared environment variables
├── firebase_key.json         # Firebase service account (not committed)
├── firebase_db.py            # Shared Firestore helper
├── Dockerfile                # Cloud Run container
├── requirements.txt          # Python dependencies
├── deploy.sh                 # Deployment script
└── README.md                 # This file
```

## 🔧 Configuration

### Environment Variables

| Variable | Agent | Description | Required |
|----------|-------|-------------|----------|
| `GOOGLE_API_KEY` | Both | Gemini API key | Yes |
| `GOOGLE_GENAI_USE_VERTEXAI` | Both | Use Vertex AI (0=No, 1=Yes) | Yes |
| `GOOGLE_PROJECT_ID` | FaqAssistant | Firebase project ID | Yes |
| `FIREBASE_KEY_PATH` | FaqAssistant | Path to service account JSON | Local only |
| `DEMO_MODE` | FaqAssistant | Enable demo purchases | No (default: true) |
| `GITHUB_TOKEN` | RepoWeightBuddy | Avoids GitHub API rate limits; required for private repos | No |
| `BROWSER_USE_API_KEY` | RepoWeightBuddy | Enables web verification step via Browser Use | No |

### Product Catalog

Products are stored in Firestore under the `products` collection:
- `prod_001` - SmartBudget Pro
- `prod_002` - SmartBudget Basic
- `prod_003` - SmartBudget Family
- `prod_004` - SmartBudget Business
- `prod_005` - SmartBudget Student

## 🧪 Testing

Test the deployed agent:

```bash
# Health check
curl https://your-url.run.app/health

# Ask about products
curl -X POST https://your-url.run.app/run \
  -H "Content-Type: application/json" \
  -d '{"app_name": "FaqAssistant", "new_message": "Tell me about SmartBudget Pro"}'
```

## 📊 Monitoring

View logs:
```bash
gcloud run services logs read faqsmartbuddy-agent \
  --project your-project-id \
  --region us-central1
```

## 💰 Cost Optimization

- **Min instances**: 0 (scales to zero when idle)
- **Max instances**: 3 (prevents runaway costs)
- **Memory**: 1Gi
- **CPU**: 1

You only pay for actual request processing time.

## 🛠️ Tech Stack

- **ADK** - Google Agent Development Kit
- **Gemini 2.5 Flash** - LLM for inference
- **FastAPI** - HTTP server (via ADK)
- **Firestore** - NoSQL database
- **Cloud Run** - Serverless deployment
- **Docker** - Containerization

## 📝 License

This project is for educational purposes.

## 🤝 Contributing

This is a mini project for demonstration purposes. Feel free to fork and extend!

