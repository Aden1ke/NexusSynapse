# Digital Employee — AI-Powered Multi-Agent DevOps System

> Microsoft AI Dev Days Global Hackathon 2026  
> Targeting: **Agentic DevOps Grand Prize** + **Best Multi-Agent System Prize**

---

## What We Built

A **Digital Employee** — a team of AI agents that works like a real software team.
You give it a task like *"Fix the bug in the checkout API and deploy it"*, and it
handles everything automatically: writing code, reviewing it, and deploying to Azure —
pausing to ask a human for approval before anything goes live.

---

## How It Works
```
You (the human)
      |
  [Manager Agent]       ← "Tech Lead". Plans the work and delegates it.
      |
      ├──→ [Coder Agent]          ← Writes the code via GitHub MCP Server
      |          |
      ├──→ [Senior Coder Agent]   ← Reviews code. Rejects if bugs/security issues found.
      |          |                   Sends back to Coder with feedback if rejected.
      |          |
      └──→ [Deployer Agent]       ← Deploys to Azure — but ONLY after asking YOU first.
```

### HITL Gate (Human-in-the-Loop)

Before any deployment, the system **stops and asks you**:
```
============================================================
  HUMAN-IN-THE-LOOP APPROVAL REQUIRED
============================================================
  Task: Fix authentication bug in login API
  Senior Coder has APPROVED this code.
  Approve deployment to production? (yes/no):
```

---

## Repo Structure
```
your-repo/
├── README.md                     ← This file
├── requirements.txt              ← Python packages (pip install -r requirements.txt)
├── .env.example                  ← Credential template — safe to commit
├── .env                          ← Your real credentials — NEVER commit this
├── .gitignore                    ← Ignores .env, __pycache__, etc.
│
├── agents/
│   ├── manager/run.py            ← START HERE. Launches the whole agent system.
│   ├── coder/agent.py            ← Writes code using GitHub MCP Server
│   ├── senior-coder/agent.py     ← Reviews code, returns APPROVED or REJECTED + feedback
│   ├── deployer/agent.py         ← HITL gate + deploys to Azure via Azure MCP Server
│   └── workflows/
│       ├── ci.yml                ← GitHub Actions: lint + test on every push
│       └── deploy.yml            ← GitHub Actions: auto-deploy to Azure on merge to main
│                                    (copy both files to .github/workflows/ in your repo)
│
├── mcp/
│   └── mcp_config.json           ← Connects agents to GitHub MCP + Azure MCP servers
│
├── infra/
│   └── azure/main.bicep          ← Creates FREE Azure App Service with one command
│
└── docs/
    └── AZURE_SETUP.md            ← Full setup guide: Azure, Foundry, secrets, branches
```

---

## Tech Stack

| Technology | Purpose | Cost |
|---|---|---|
| Azure AI Foundry | Hosts all agents, provides gpt-4o | Pay-per-token |
| Microsoft Agent Framework (Python) | Orchestrates agent conversations | Free |
| GitHub MCP Server | Coder agent reads/writes repo files | Free |
| Azure MCP Server | Deployer agent runs Azure commands | Free |
| GitHub Actions | CI/CD pipeline | Free for public repos |
| Azure App Service F1 | Hosts the deployed app | Always free |
| OpenTelemetry | Traces agent conversation flow | Free |

---

## Quick Start
```bash
# 1. Clone and install
git clone https://github.com/YOUR-ORG/YOUR-REPO.git
cd YOUR-REPO
pip install -r requirements.txt

# 2. Add credentials
cp .env.example .env
# Open .env and fill in values — see docs/AZURE_SETUP.md

# 3. Run
python agents/manager/run.py
```

---

## Example Agent Conversation
```
[You]           "Fix the bug in the checkout API."
[Manager]       Planning... delegating to Coder Agent.
[Coder]         Writing fix... submitted for review.
[Senior Coder]  REJECTED. Missing try/catch on line 42. Resubmit.
[Coder]         Fixed. Resubmitting.
[Senior Coder]  APPROVED. Score: 91/100. Forwarding to Deployer.
[System]        *** HUMAN APPROVAL REQUIRED — Approve deployment? (yes/no): yes
[Deployer]      Deploying... DONE. Live at https://your-app.azurewebsites.net
```

---

## Team

| Name | Responsibility |
|------|----------------|
| Member 1 | Agent Framework + Orchestration |
| Member 2 | MCP Server Integration |
| Member 3 | Azure Infra + Deployment |
| Member 4 | Frontend + Demo Video |

---

## Demo Video

> https://youtu.be/DzrJkngt7JQ?si=6xf8YW3dEfJttv3v
---

## Submission Checklist

- [ ] Public GitHub repo with this README
- [ ] Demo video link added (YouTube/Vimeo, under 2 min)
- [ ] All agents tested and functional
- [ ] `.env.example` committed (never `.env`)
- [ ] Branch protection rules enabled on `main`
- [ ] CI workflow passing on latest commit
- [ ] Azure deployment working end-to-end

---

## License

MIT
