# Production Management System
A database-driven **Production Management System (ERP)** built for a leather manufacturing enterprise (Le Mieux Ltd) using Python, Django, and the AdminLTE dashboard framework.

---

## Core Features

1. **Active Workload Dashboard:** Real-time summary cards, overdue task alerts, and an active employee\artisan workload radar.
2. **Dynamic BOM & Cost Prediction:** Links products to raw materials via inline formsets, automatically calculating predicted production costs and profit margins.
3. **Automated Inventory Stock Control:** Cross-references required Bill of Materials (BOM) against warehouse stock upon task creation, automatically deducting or refunding materials through custom model overrides.
4. **Human Resources (HR) Management:** Manages artisan rosters, active contract types, and real-time leave requests. Automatically blocks managers from assigning tasks to staff on approved leave.
5. **State Machine & Validation:** Enforces strict workflow rules (e.g., tasks with progress cannot be "Pending", completed tasks must match target quantities). Handles database integrity gracefully using `ProtectedError` exceptions.
6. **Modern UI & UX Interactivity:** Fully responsive DataTables (instant search filtering, column sorting, pagination), persistent Dark/Light Mode via local storage, and DRY shared components.

---

## Tech Stack

* **Backend:** Python, Django
* **Frontend:** HTML5, CSS3, Bootstrap 4, AdminLTE Template, Font Awesome
* **Database:** SQLite

---

## Project Structure

```text
production_management/
│
├── config/             # Project-level settings, URLs, and WSGI routing
├── inventory/          # Products, Raw Materials, and BOM management
├── production/         # Production Tasks, state machines, and calculations
├── employees/          # Artisans, Contracts, and Leave Requests
├── templates/          # Shared base layout, actions, and confirmation modals
├── static/             # AdminLTE styles, JavaScript plugins, and icons
├── requirements.txt     # Project dependencies
├── .gitignore           # Git ignore rules
├── db.sqlite3          # SQLite database file
├── Credentials.txt     # Default credentials
├── manage.py           # Django command-line utility
└── README.md           # Project documentation
```

---

## Getting Started & Installation

Follow these steps to run the project locally:

1. **Clone or Extract** the project repository to your local machine.
2. **Open your terminal** in the root project directory (where `manage.py` is located).
3. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   venv\Scripts\activate # On Windows:
   source venv/bin/activate # On Mac/Linux:
   ```
4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
5. **Run database migrations:**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```
6. **Create a superuser account:**
   ```bash
   python manage.py createsuperuser
   ```
   *(In our case, the credentials are on `Credentials.txt file`).*
7. **Start the development server:**
   ```bash
   python manage.py runserver
   ```

8. Open your web browser and navigate to **`http://127.0.0.1:8000/`**.

---

## Group Members:
* **Iradukunda Muhire Bertin** (20251MBI046)
* **Isaac Nkusi** (20251MBI020)
* **Rwabukanga Jean de Dieu** (20251MBI010)

*Big Data Analytics, Adventist University of Central Africa (AUCA).*