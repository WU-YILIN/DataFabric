
# Genesis Frontend Plan

## 1. Design System (iOS Style)
*   **Philosophy**: Depth, Translucency, Blur (Glassmorphism), Rounded Corners (20px+).
*   **Typography**: San Francisco (System UI).
*   **Colors**:
    *   Background: `bg-slate-50` or dynamic gradients.
    *   Surface: `bg-white/70` with `backdrop-blur-xl`.
    *   Primary: `indigo-500` (Vibrant).
*   **Interactions**: Spring animations, hover lifts.

## 2. Architecture
*   **Framework**: React + Vite + TypeScript.
*   **State**: Local state + Context (if needed).
*   **Services**: `src/services/` decoupled from UI.

## 3. Pages & Features

### 3.1 Dashboard (`/`)
*   **KPIS**: Total Events, Governance Score, Avg Latency.
*   **Activity Feed**: Recent governance checks.

### 3.2 Governance (`/governance`)
*   **Input**: Event Code, Name, Schema, Description.
*   **Action**: "Arbitrate" (Calls LLM).
*   **Output**: Verdict (Approve/Reject), Confidence Score, Reasoning.

### 3.3 Event Registry (`/events`)
*   **List View**: Searchable list of all TrackingEvents.
*   **Detail View**: JSON Schema viewer.
*   **Actions**: Filter by Domain, Status.

### 3.4 Audit Logs (`/logs`)
*   **Table**: Who did what and when.
*   **Filters**: Activity type, user.

### 3.5 Settings (`/settings`)
*   **Project Config**: API Keys.
*   **User Prefs**: Notification settings.