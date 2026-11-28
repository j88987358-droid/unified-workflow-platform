Unified Workflow Platform

A mobile-first platform for building, managing, executing, and monitoring different types of workflows.

Vision

Build and control workflows directly from an Android mobile browser while execution happens on remote servers.

Core Modules

1. Unified Dashboard
2. Python Code Editor
3. Visual Workflow Builder
4. Architecture Designer
5. AI Agent Manager
6. Task Monitoring
7. Multiple Server Management
8. Logs and Error Monitoring

Technology Stack

- Frontend: React
- Architecture Designer: React Flow
- Backend: Python + FastAPI
- Automation: n8n
- Workflow Orchestration: Prefect
- Database: PostgreSQL
- Code Storage: GitHub

Architecture

Android Mobile
|
Unified Dashboard
|
Central Backend (FastAPI)
|
Task Controller
|
Worker Servers
|
Central Database

Development Principles

- Mobile-first development
- Modular architecture
- Open-source technologies
- Free infrastructure where possible
- Secure server communication
- Reliable task execution
- Centralized monitoring

Development Status

Phase 1: Foundation Setup — In Progress


## Hybrid storage and execution lease notes

- Local development uses `InMemoryStorage` for task persistence and process-local leases.
- Production runtime should inject a Google Sheets task store and a shared `AppsScriptStorage` lease adapter separately.
- The Apps Script backend serializes its own requests with `LockService.getScriptLock()`; deploy one Apps Script project for the shared spreadsheet/lease namespace.
- `GoogleSheetsStorage.atomic_update()` serializes threads only within one Python process. It is not a distributed transaction across independent runners. The shared lease prevents duplicate execution of the same task, but it does not make the entire Google Sheets task collection safe for concurrent multi-runner writes. Do not claim full multi-runner persistence safety until a distributed transactional task-store adapter is added and verified.
