# PROJECT: AI Workspace Manager

I already have a bare-bones version of this project. I want you to turn it into a polished, deployable full-stack application over the next 3–4 days.

Do NOT rewrite working code unnecessarily.

First:
1. Inspect the entire existing repository.
2. Explain the current architecture briefly.
3. Identify what is already implemented, partially implemented, broken, or missing.
4. Create a short implementation plan against the specification below.
5. Then begin implementing it incrementally.
6. Preserve working functionality wherever possible.
7. After each major feature, run the relevant tests/build commands and fix failures before proceeding.

The final result should be portfolio/resume quality, not a hackathon prototype.

---

# 1. PRODUCT OVERVIEW

Build a web-based AI Workspace Manager for organizing long-running AI work into reusable projects, workflows, conversations, and prompt templates.

The application should solve a problem that ordinary chatbot interfaces handle poorly:

- conversations become disconnected;
- useful prompts are repeatedly rewritten;
- users cannot easily create reusable workflows;
- previous context becomes difficult to retrieve;
- experimenting with a different conversational direction can destroy the clean original thread;
- long-running projects need persistent structured context.

The application should allow a user to combine these resources:

Global Workflow Library
    -> attach to any Project and/or Conversation
Project (optional)
    -> Conversation
        -> Message Tree / Branch Cursors

Users should be able to create reusable workflow configurations, execute prompts through Gemini, preserve conversations in PostgreSQL, branch from any previous assistant answer, and semantically search previous interactions.

The current LLM provider is Gemini.

The backend architecture must isolate Gemini-specific code behind a provider abstraction so another provider could later be added without rewriting the application.

DO NOT implement OpenAI, Anthropic, or other providers during this build.

---

## 1.1 SUPERSEDING PRODUCT DECISIONS — SEPTEMBER 3, 2026

This section is authoritative wherever the original proposal below describes a
strict `Project -> Workflow -> Conversation` hierarchy or a raw-history branch.

1. **Workflows are global reusable skills.** A workflow is not owned by one
   project. Projects and conversations may each attach multiple workflows using
   ordered many-to-many links. A conversation may inherit its project's attached
   workflows and add direct workflows of its own.
2. **Projects are optional for conversations.** A user can start a standalone
   general chat, with or without a workflow, and may later file it into a project.
3. **Branches have explicit cursors.** Messages remain one immutable parent-linked
   tree. A branch stores its parent branch, fork message, head message, name, and
   relevance snapshot; it does not duplicate shared messages.
4. **Branch creation is instant and starts from an answer.** Only assistant answers
   are branch anchors. Creating a branch stores a cursor immediately without calling
   Gemini or requiring a first message. The selected answer is the first visible
   item; earlier source history remains hidden in the backend. When the user sends
   the first prompt on that branch, Gemini receives the source context and creates
   a relevance-pruned snapshot before answering. Unrelated material is omitted from
   later branch AI context but never deleted from stored history.
5. **References to omitted context are detected before persistence.** Before a
   later message is saved on a non-main branch, Gemini checks whether it materially
   depends on source information absent from the branch snapshot. If so, the app
   preserves the draft and asks the user to start a fresh sibling branch from the
   main trunk, continue on the current branch, or dismiss the suggestion. No tree
   mutation occurs until the user chooses.
6. **Conversation-level model settings resolve conflicts.** Workflow model settings
   act as defaults. The conversation stores the effective model and temperature so
   combining multiple workflows is deterministic.
7. **Deletion preserves reusable work.** Deleting a project detaches workflow links
   and makes its conversations standalone; global workflows and conversations are
   not cascade-deleted.
8. **Titles refresh only at branch creation.** A new branch receives an immediate
   provisional local name so branching never waits for Gemini. One best-effort
   background Gemini request then generates the new branch title and recomputes the
   conversation title from all branch names. Sending ordinary replies does not
   regenerate titles.
9. **Chat messages render safe GitHub-flavored Markdown.** Assistant and user
   message content supports headings, emphasis, lists, code, links, and tables.
   Raw HTML is not interpreted.
10. **Regular chat search covers stored content.** The Chats page can perform a
    case-insensitive substring search across conversation titles and every message
    stored in every branch. Semantic/vector ranking remains a future enhancement.
11. **Branch context guides but does not confine answers.** Gemini uses the active
    snapshot for prior user-specific facts and decisions, while new or unrelated
    questions are answered normally from the model's own capabilities. The UI shows
    an animated generation state, a live elapsed timer, and the completed generation
    time saved with each assistant reply.
12. **Omitted branch context is reversible.** The active-context card explains that
    omitted topics remain stored, lets the user select omitted topic labels, and asks
    Gemini to rebuild the snapshot with the selected source material restored.

---

# 2. TECHNOLOGY STACK

Keep/use:

Frontend:
- React
- JavaScript or TypeScript depending on the existing project
- Prefer TypeScript if the project already uses it
- React Router if routing is needed
- fetch or the project's existing HTTP client

Backend:
- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic migrations if practical with the existing architecture

Database:
- PostgreSQL

AI:
- Gemini API
- Official currently-supported Gemini Python SDK
- model name configurable through environment variables

Semantic search:
- PostgreSQL + pgvector
- Gemini embedding API through the same AI service layer

Deployment:
- frontend: Vercel
- backend: Railway or Render
- PostgreSQL: managed PostgreSQL on the chosen backend platform

Developer infrastructure:
- .env configuration
- .env.example
- Dockerfile for backend
- requirements.txt or pyproject.toml, whichever the project already uses
- README with local development and deployment instructions

Do NOT introduce unnecessary infrastructure such as:
- Kubernetes
- microservices
- Kafka
- Celery
- Redis
- message queues
- complex authentication systems
- separate vector databases

This should remain a clean monolithic FastAPI backend with a React frontend.

---

# 3. MVP SUCCESS CRITERIA

The deployed application must support this complete workflow:

1. User opens the application.
2. User creates a Project.
3. User creates or selects a Workflow.
4. User configures:
   - workflow name
   - description
   - system prompt
   - reusable prompt template
   - model settings where appropriate
5. User starts a Conversation under that workflow.
6. User sends a message.
7. FastAPI receives the request.
8. Relevant persistent context is assembled.
9. Gemini generates the response.
10. User and assistant messages are stored in PostgreSQL.
11. User continues the conversation.
12. User can leave and later return to the conversation.
13. Conversation history remains available.
14. User can branch from an earlier message.
15. The branch becomes a new conversational path without modifying the original path.
16. User can search historical messages using semantic search.
17. Search results link back to the source conversation.
18. User can reuse an existing workflow to create another conversation.
19. Application is deployed publicly.
20. Production application works after a fresh browser reload.

That vertical slice is more important than adding additional features.

---

# 4. CORE DOMAIN MODEL

Use the following conceptual hierarchy.

## Project

Represents a long-running area of work.

Examples:
- Equity Research
- Software Project
- Job Search
- Research Project

Fields:

id
name
description
created_at
updated_at

A Project has many Workflows.

---

## Workflow

A reusable AI configuration belonging to a Project.

Fields:

id
project_id
name
description
system_prompt
prompt_template
model_name
temperature
created_at
updated_at

A Workflow should be reusable.

Creating a conversation from a workflow should not destroy or mutate previous conversations.

Example:

Workflow:
"Equity Research Analyst"

System prompt:
"You are an equity research assistant. Analyze companies using evidence, separate facts from assumptions, and focus on business economics, financial performance, valuation, competitive positioning, and risks."

Prompt template:
"Analyze {{company}} with emphasis on {{focus_area}}."

The application does NOT need a complicated drag-and-drop workflow engine.

A workflow is simply a saved reusable AI configuration.

That distinction is important.

---

## Conversation

Represents one AI session under a workflow.

Fields:

id
project_id
workflow_id
title
created_at
updated_at

Optional:

parent_conversation_id

if useful for branch tracking.

A Project can contain many Conversations.

A Workflow can generate many Conversations.

---

## Message

Fields:

id
conversation_id
parent_message_id nullable
role
content
created_at
embedding if appropriate
metadata JSON/JSONB if useful

role should support at minimum:

user
assistant
system if needed internally

parent_message_id enables conversation branching.

---

# 5. CONVERSATION BRANCHING

This is one of the main differentiating features and must actually work.

Users should be able to select an earlier message and choose:

"Branch from here"

Example original conversation:

M1 User
 |
M2 Assistant
 |
M3 User
 |
M4 Assistant
 |
M5 User

If the user branches from M2:

M1
 |
M2
 | \
M3  B1
 |    |
M4   B2
 |
M5

The original M3 -> M4 -> M5 chain must remain unchanged.

The branch should create a separate conversational path.

Implementation:

Every message may have:

parent_message_id

When generating an AI response:

1. Start from the selected/current message.
2. Traverse parent_message_id backward.
3. Reconstruct the path to the root.
4. Reverse it into chronological order.
5. Send only that path to Gemini.

Do NOT send messages belonging to sibling branches.

The frontend does not need a sophisticated graphical tree.

A simple branch indicator is enough.

For example:

Conversation
 ├ Original
 ├ Branch 1
 └ Branch 2

or a small branch selector above the conversation.

Prioritize correct backend behavior over fancy visualization.

---

# 6. PERSISTENT CONTEXT MANAGEMENT

The application should support persistent project context.

Do not attempt to build autonomous long-term memory.

Instead implement deterministic context assembly.

When sending a message, construct Gemini context from:

1. workflow system prompt
2. relevant workflow configuration
3. current branch conversation history
4. optionally retrieved relevant historical messages from the same project
5. current user message

Create a dedicated service:

ContextBuilder

Example conceptual interface:

build_context(
    project_id,
    workflow_id,
    conversation_id,
    current_message
)

The LLM route itself should NOT contain a giant block of context-management logic.

Keep context assembly separated from Gemini calls.

---

# 7. SEMANTIC SEARCH

Implement semantic search across stored conversation messages.

This must be a working feature, not a UI placeholder.

Use:

Gemini embedding model
+
PostgreSQL pgvector

On message creation:

1. Save message.
2. Generate an embedding for useful user/assistant textual messages.
3. Store embedding in PostgreSQL.

Search flow:

User enters:

"what did we discuss about Tesla margins?"

Backend:

1. Generate query embedding.
2. Run vector similarity search against messages.
3. Prefer messages from the selected Project.
4. Return top relevant results.

Each result should include:

message content
conversation title
project
timestamp
similarity/relevance information if useful
conversation_id
message_id

Frontend search results should be clickable and navigate to the corresponding conversation.

Keep search simple.

No RAG framework such as LangChain or LlamaIndex is required.

Implement the retrieval logic directly.

If pgvector causes deployment problems that cannot be resolved quickly, preserve the search-service abstraction and implement PostgreSQL full-text search as a temporary fallback, but pgvector is the intended implementation.

---

# 8. LLM PROVIDER ARCHITECTURE

Do NOT call Gemini directly from API route files.

Create something conceptually similar to:

backend/
    services/
        llm/
            base.py
            gemini.py
            factory.py

Example interface:

class LLMProvider:
    async def generate(self, messages, config):
        ...

    async def embed(self, text):
        ...

GeminiProvider implements that interface.

The rest of the application should interact with:

LLMProvider

rather than Gemini directly.

Provider selection may currently always return Gemini.

This deliberately prepares the architecture for future support for:

- OpenAI
- Anthropic
- local models

without implementing those integrations now.

---

# 9. PROMPT TEMPLATES

Users should be able to save reusable prompt templates as part of workflows.

Minimum functionality:

- system prompt
- reusable user prompt template
- editable workflow configuration

Optionally support simple variables:

{{company}}
{{task}}
{{focus_area}}

Do NOT build a complicated template engine.

A simple variable substitution implementation is enough.

If variables are detected, the frontend may request values before starting the conversation.

If this adds too much complexity relative to the existing code, prioritize editable saved templates over variable forms.

---

# 10. BACKEND API

Use REST APIs.

Adapt endpoint names to the existing backend if appropriate.

Desired endpoint structure:

GET    /health

PROJECTS

GET    /api/projects
POST   /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}

WORKFLOWS

GET    /api/projects/{project_id}/workflows
POST   /api/projects/{project_id}/workflows
GET    /api/workflows/{workflow_id}
PATCH  /api/workflows/{workflow_id}
DELETE /api/workflows/{workflow_id}

CONVERSATIONS

GET    /api/projects/{project_id}/conversations
POST   /api/workflows/{workflow_id}/conversations
GET    /api/conversations/{conversation_id}
DELETE /api/conversations/{conversation_id}

MESSAGES

GET    /api/conversations/{conversation_id}/messages
POST   /api/conversations/{conversation_id}/messages

BRANCHING

POST /api/messages/{message_id}/branch

or another clean equivalent.

SEARCH

POST /api/search

body:

{
    "query": "...",
    "project_id": optional,
    "limit": 10
}

The API should use sensible request/response models.

Return appropriate HTTP status codes.

Do not expose raw database exceptions.

---

# 11. DATABASE

Create normalized PostgreSQL tables.

Minimum:

projects
workflows
conversations
messages

Add indexes where useful.

Important indexes:

workflows.project_id
conversations.project_id
conversations.workflow_id
messages.conversation_id
messages.parent_message_id

Create vector index only if supported cleanly by pgvector and current database configuration.

Use proper foreign keys.

Use cascade behavior carefully.

Deleting a Project may delete its Workflows, Conversations, and Messages if that is the chosen product behavior.

Document that decision.

Use timestamps consistently.

Use UUIDs if the current repository already uses them.

Do not rewrite the application's ID strategy solely for this project upgrade.

---

# 12. FRONTEND

The frontend should look like a real productivity application.

Do NOT spend a day on visual design.

Use a clean three-region layout.

Example:

------------------------------------------------
| Sidebar | Main Workspace                   |
|         |                                  |
|Projects | Conversation / Workflow          |
|         |                                  |
|Workflow |                                  |
|s        |                                  |
|         |                                  |
|Chats    |                                  |
------------------------------------------------

Suggested sidebar:

AI Workspace

[+ New Project]

PROJECTS
> Equity Research
    Workflows
      Equity Analyst
      Earnings Review

    Conversations
      NVIDIA Analysis
      Canadian Banks

Search

Main area should display either:

- project overview
- workflow configuration
- conversation interface
- search results

Conversation UI:

Title

Workflow: Equity Analyst

----------------------------------
User:
...

Assistant:
...
----------------------------------

[ message input                    ]
[ Send ]

Each eligible message should have subtle actions:

Branch
Copy

Show a loading indicator while waiting for Gemini.

Disable duplicate sends while a request is pending.

Display useful error messages.

Do not expose stack traces.

---

# 13. PROJECT DASHBOARD

When a Project is opened, show:

Project name
Project description

Workflows
Recent conversations

Buttons:

New Workflow
New Conversation

Optionally:

number of conversations
last updated

Do NOT build analytics dashboards.

---

# 14. WORKFLOW EDITOR

Create a simple form:

Name
Description
System Prompt
Prompt Template
Gemini Model
Temperature

Buttons:

Save Workflow
Start Conversation

Make system prompts and prompt templates large text areas.

Workflow edits should affect future requests using that workflow.

Do not retroactively rewrite old messages.

---

# 15. CHAT BEHAVIOR

When user sends a message:

Frontend
    ->
POST message
    ->
FastAPI
    ->
save user message
    ->
ContextBuilder
    ->
LLMProvider
    ->
GeminiProvider
    ->
save assistant message
    ->
generate/store embeddings
    ->
return assistant message
    ->
frontend updates

Handle failures correctly.

If Gemini fails:

- do not create a fake assistant response;
- keep the user's message;
- return a useful error;
- allow retrying.

Do not silently swallow exceptions.

---

# 16. CONVERSATION TITLES

When a new conversation is created:

Allow user to provide a title.

If blank, create a simple title from the first user message.

Do not spend time implementing another LLM call solely for title generation unless trivial.

---

# 17. ERROR HANDLING

Backend should handle:

- nonexistent project
- nonexistent workflow
- nonexistent conversation
- invalid parent message
- Gemini API failure
- embedding API failure
- database failure
- malformed input

Embedding failure should ideally not prevent the chat response from being saved.

Log the embedding failure and continue.

Semantic search for that message simply will not include the missing embedding until repaired.

---

# 18. CONFIGURATION

All secrets must come from environment variables.

Example:

DATABASE_URL=
GEMINI_API_KEY=
GEMINI_CHAT_MODEL=
GEMINI_EMBEDDING_MODEL=
FRONTEND_URL=
ENVIRONMENT=

Do not commit .env.

Create:

.env.example

with safe placeholder values.

---

# 19. SECURITY / BASIC PRODUCTION HYGIENE

This is a portfolio deployment, not a banking application.

Implement:

- environment-based secrets
- CORS restricted to frontend deployment URL in production
- request validation through Pydantic
- parameterized database access through ORM
- basic input size restrictions where sensible
- no secrets sent to frontend
- no Gemini API key in React environment variables
- useful server logs

Do NOT implement a major identity/authentication system unless one already exists.

For the initial deployed portfolio version, assume a single-user workspace if necessary.

Document this limitation clearly.

---

# 20. TESTING

Do not attempt exhaustive test coverage.

Add a focused backend test suite for the highest-value logic.

At minimum test:

1. project creation
2. workflow creation
3. conversation creation
4. message persistence
5. branch construction
6. context path reconstruction
7. branch isolation
8. search service behavior where practical

Mock Gemini in tests.

Tests must not require paid API calls.

The most important test is conversation branching.

Example assertion:

Given:

A -> B -> C
     \
      D -> E

Context for E must be:

A, B, D, E

and MUST NOT contain:

C

---

# 21. CODE QUALITY

Use clear separation such as:

backend/
    api/
    models/
    schemas/
    services/
        llm/
        context/
        search/
    db/
    main.py

Do not force this exact structure if the repository already has a reasonable architecture.

Prefer adapting the existing architecture rather than performing a gratuitous rewrite.

Keep route handlers thin.

Business logic belongs in services.

Database logic should not be duplicated across routes.

Use descriptive names.

Remove obvious dead code.

Do not over-engineer.

---

# 22. DEPLOYMENT

The application must actually be deployed.

Frontend:

Vercel

Backend:

Railway or Render

Database:

Managed PostgreSQL

Required production behavior:

- frontend uses backend production URL
- backend CORS accepts deployed frontend
- database persists after redeploys
- application survives page refresh
- secrets are configured through platform environment variables
- /health returns successful status
- Gemini calls work in production
- semantic search works in production

Create deployment instructions in README.

Also create:

Dockerfile

for the backend.

---

# 23. README

Write a serious GitHub README.

Include:

# AI Workspace Manager

Short description.

## Problem

Explain why ordinary linear chatbot interfaces become difficult for long-running projects.

## Features

- Projects
- Reusable AI workflows
- Configurable prompt templates
- Persistent conversations
- Conversation branching
- Context management
- Semantic search
- Modular LLM provider architecture
- Gemini integration

## Architecture

Include a simple diagram:

React
   |
   | REST
   v
FastAPI
   |
   +--> Context Builder
   |
   +--> LLM Provider --> Gemini
   |
   +--> Search Service --> Gemini Embeddings
   |
   v
PostgreSQL + pgvector

## Conversation Branching

Explain parent-message tree architecture.

## Tech Stack

React
FastAPI
PostgreSQL
pgvector
Gemini API

## Local Setup

Exact commands.

## Environment Variables

Document them.

## Testing

Exact commands.

## Deployment

Explain Vercel + backend deployment.

## Future Improvements

- additional LLM providers
- shared workspaces
- authentication
- document/file context
- automated context summarization
- richer branch visualization
- usage/cost tracking

Do NOT claim those future features are currently implemented.

---

# 24. OPTIONAL UI POLISH

Only after core functionality works:

- responsive sidebar
- empty states
- loading skeleton/spinner
- toast notifications
- timestamps
- copy message button
- delete confirmation
- keyboard shortcut: Enter to send, Shift+Enter newline
- active project/workflow highlighting

Do not allow polish to delay deployment.

---

# 25. FEATURES EXPLICITLY OUT OF SCOPE

Do NOT implement during this 3–4 day build:

- multiple LLM providers
- agentic tool execution
- autonomous agents
- team collaboration
- billing
- payments
- complicated permissions
- file upload / document RAG
- web browsing
- voice
- mobile app
- drag-and-drop workflow builders
- complex workflow DAGs
- real-time collaboration
- WebSockets unless already necessary
- Redis
- queues
- background-worker infrastructure
- custom model training

The architecture may make future implementation possible, but the features themselves must not consume development time.

---

# 26. PRIORITY ORDER

Implement in this exact order unless existing code substantially changes the dependencies.

P0 — MUST WORK

1. inspect/fix existing project
2. PostgreSQL models
3. Project CRUD
4. Workflow CRUD
5. Conversation CRUD
6. Gemini provider abstraction
7. send/receive messages
8. message persistence
9. reload conversations
10. deployment

P1 — DIFFERENTIATING FEATURES

11. conversation branching
12. branch-safe context reconstruction
13. Gemini embeddings
14. pgvector semantic search
15. search UI

P2 — PORTFOLIO QUALITY

16. workflow editor
17. error handling
18. focused tests
19. Dockerfile
20. README
21. UI polish

If time runs out, sacrifice P2 cosmetic work before sacrificing branching or persistence.

---

# 27. DEVELOPMENT SCHEDULE

Treat this as a four-day maximum project.

DAY 1 — FOUNDATION

Goal:
A complete persistent Project -> Workflow -> Conversation system.

Tasks:

- inspect repository
- clean obvious blockers
- finalize database schema
- configure PostgreSQL
- create migrations
- Project CRUD
- Workflow CRUD
- Conversation CRUD
- build frontend navigation
- connect frontend to backend
- verify persistence

End-of-day requirement:

I can create a project, create a workflow, create a conversation, refresh the browser, and everything remains.

---

DAY 2 — AI CHAT + BRANCHING

Goal:
Make the application meaningfully different from a normal chatbot.

Tasks:

- implement LLMProvider abstraction
- implement GeminiProvider
- create ContextBuilder
- implement message persistence
- implement AI responses
- render conversation history
- implement parent_message_id
- implement branch creation
- reconstruct branch-specific context
- add branch selector/UI
- add branching tests

End-of-day requirement:

I can hold a Gemini conversation, refresh it, branch from an old message, continue down two different paths, and neither branch contaminates the other.

---

DAY 3 — SEARCH + DEPLOYMENT

Goal:
Finish the second differentiating feature and get production online.

Tasks:

- configure pgvector
- create embeddings
- store embeddings
- implement search service
- implement project-scoped semantic search
- build search interface
- make results navigate to conversations
- create production environment config
- Dockerize backend
- deploy backend
- deploy PostgreSQL
- deploy frontend
- configure CORS
- verify Gemini in production

End-of-day requirement:

The live application supports persistent AI conversations, branching, and semantic search.

---

DAY 4 — HARDENING

Goal:
Turn the functional app into something I can send to a recruiter.

Tasks:

- fix production bugs
- improve error states
- improve empty states
- test core API
- mock Gemini tests
- validate branch isolation
- clean UI
- remove dead/debug code
- add README
- architecture diagram
- deployment instructions
- take screenshots
- verify a fresh user/browser can understand the product

Do NOT add major new features on Day 4.

---

# 28. DEMO DATA

Create useful sample content, but do not permanently hard-code demo data into production.

Suggested demo:

Project:
Equity Research

Workflow:
Fundamental Equity Analyst

Description:
Reusable workflow for researching public companies.

System Prompt:
"You are an equity research assistant. Analyze businesses using evidence and clearly distinguish reported facts, calculations, assumptions, and conclusions. Focus on business model, competitive positioning, financial performance, valuation drivers, catalysts, and risks."

Conversation 1:
NVIDIA Investment Thesis

Conversation 2:
Canadian Banks Comparison

This demonstrates that one Project can contain reusable workflows and multiple research threads.

---

# 29. DEMO SCRIPT

The finished application should support a 60–90 second portfolio demonstration:

1. Open deployed application.
2. Open "Equity Research" project.
3. Show reusable "Fundamental Equity Analyst" workflow.
4. Start a new conversation.
5. Ask a company-analysis question.
6. Show Gemini response.
7. Continue conversation.
8. Branch from the earlier response.
9. Ask a different follow-up.
10. Switch between branches to demonstrate isolation.
11. Search for a concept discussed in another conversation.
12. Open the matching semantic-search result.
13. Briefly show architecture in README.

The application's value should be obvious without a five-minute explanation.

---

# 30. FINAL ACCEPTANCE CHECKLIST

Before considering the project complete, verify all of these manually.

[ ] frontend builds
[ ] backend starts
[ ] PostgreSQL connects
[ ] migrations work from clean database
[ ] create Project works
[ ] edit Project works
[ ] create Workflow works
[ ] edit Workflow works
[ ] create Conversation works
[ ] send message works
[ ] Gemini responds
[ ] messages persist
[ ] browser refresh preserves state
[ ] branching works
[ ] sibling branches remain isolated
[ ] embeddings are generated
[ ] semantic search returns relevant previous messages
[ ] search results link to conversations
[ ] API errors are user-friendly
[ ] Gemini failures do not corrupt conversations
[ ] backend tests pass
[ ] frontend production build passes
[ ] backend deployed
[ ] database deployed
[ ] frontend deployed
[ ] production Gemini request works
[ ] production search works
[ ] README reflects ACTUAL functionality
[ ] no API keys in repository
[ ] no fake functionality
[ ] no dead placeholder buttons

---

# 31. IMPORTANT IMPLEMENTATION RULES

Do not create fake functionality just to satisfy the UI.

Do not label something "semantic search" if it is merely substring matching unless pgvector has genuinely proven impossible within the available deployment environment.

Do not claim multi-provider support. Implement a provider abstraction and Gemini provider.

Do not claim autonomous memory. Implement persistent deterministic context management.

Do not turn workflow profiles into an over-engineered automation system.

Do not rewrite the repository from scratch unless the current architecture is genuinely unusable and you explain why first.

Do not add dependencies without a reason.

Prefer boring, understandable implementation choices.

Prioritize:
correctness
> deployed functionality
> maintainability
> UI polish
> additional features.

When an implementation decision is ambiguous, choose the simplest architecture that preserves the features in this specification.

---

# 32. WHEN YOU FINISH

Provide:

1. summary of architecture
2. implemented feature list
3. exact local startup commands
4. database migration commands
5. test commands
6. deployment procedure
7. required environment variables
8. known limitations
9. future improvements
10. repository cleanup recommendations

Then inspect the repository one final time for:

- exposed secrets
- TODO placeholders
- console debugging
- dead code
- broken links
- incorrect README claims
- unused dependencies
- missing error handling

Do not declare the project finished until the production build and core tests pass.
