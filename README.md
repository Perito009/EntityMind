# EntityMind

EntityMind is an AI-powered facial recognition system for real-time people counting and analytics. It provides a modern web dashboard, user management, and system configuration, built with FastAPI (backend) and React (frontend).

## Features

- Real-time people counting using facial recognition
- Live dashboard with analytics and historical data
- User authentication (JWT) and role-based access (admin/viewer)
- User management (admin only)
- System settings and configuration
- WebSocket support for live updates
- RESTful API for integration and automation

## Tech Stack

- **Backend:** FastAPI, MongoDB, Redis, OpenCV, Motor, JWT, Passlib
- **Frontend:** React, Tailwind CSS, Chart.js, Axios, React Router
- **WebSocket:** FastAPI native WebSocket endpoints

## Requirements

- Python 3.8+
- Node.js 16+
- MongoDB
- Redis

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/your-org/entitymind.git
cd entitymind
```

### 2. Backend Setup

#### a. Create and activate a virtual environment

```bash
cd backend
python -m venv venv
source venv/bin/activate
```

#### b. Install dependencies

```bash
pip install -r requirements.txt
```

#### c. Configure environment variables

Copy `.env` and adjust as needed:

```bash
cp .env.example .env
# Edit .env for your MongoDB/Redis/JWT settings
```

#### d. Start MongoDB and Redis

Make sure MongoDB and Redis are running locally or update `.env` with your connection strings.

#### e. Run the backend server

```bash
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### 3. Frontend Setup

```bash
cd ../frontend
npm install
```

#### a. Configure environment variables

Edit `.env` if needed (defaults to local backend).

#### b. Start the frontend

```bash
npm start
```

The frontend will be available at [http://localhost:3000](http://localhost:3000).

## Default Admin Credentials

- **Username:** `admin`
- **Password:** `admin123`

Change these after first login for security.

## Usage

- Access the dashboard at [http://localhost:3000](http://localhost:3000)
- Login with your credentials
- Admins can manage users and settings
- The dashboard displays real-time people count and analytics

## API Endpoints

- `POST /api/auth/login` — Obtain JWT token
- `GET /api/users/me` — Get current user profile
- `GET /api/count/current` — Get current people count
- `GET /api/count/history` — Get historical count data
- `POST /api/process/frame` — Upload image for face detection
- `POST /api/simulate/count` — Simulate people count (testing)
- `GET /api/health` — Health check
- `WS /ws/live-count` — WebSocket for live count updates

## Development

- Backend: FastAPI auto-reloads with `--reload`
- Frontend: React dev server auto-reloads on changes
- Code is formatted with Black (Python) and Prettier (JS)

## License

MIT License

---

**Note:** This project is for demonstration and MVP purposes. For production, secure your environment variables, use HTTPS, and review authentication and data privacy best practices.