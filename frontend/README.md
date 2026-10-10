# Flood Risk Dashboard frontend

React (via Vite) frontend for the Dashboard module (proposal 3.6.6),
talking to the Flask backend in `../backend/` rather than Flask
templates. This first slice is a login screen plus a plain data
explorer, enough to sign in as a real user and see the raw response of
every `routes_dashboard.py` endpoint. It is deliberately unstyled: the
catchment map, alert management screen and the other designed views
from 3.4.6 are later work, not this commit.

## Running it

With the backend running (`cd ../backend && python app.py`, listening
on `API_PORT`, 5001 by default per `backend/config.py`):

```
npm install
npm run dev
```

Vite's dev server is pinned to port 5173 (`vite.config.js`), because
the backend's CORS allow-list (`FRONTEND_ORIGINS` in `backend/config.py`)
names that exact origin. If 5173 is unavailable, change the port in
both places together, not just one.

Sign in with a user created via `../backend/create_user.py`. Only a
`system_administrator` sees the "Users" endpoint, since
`routes_dashboard.py` restricts `/api/users` to that role specifically.

## Why a login screen first

`backend/routes_auth.py`'s session-based login already existed, but
with no frontend there was no way to exercise it, or the new dashboard
endpoints, from a browser; hitting them directly produced either a 401
with no way to authenticate, or (on macOS, before `API_PORT` was added)
a confusing 403 from AirPlay Receiver squatting on the old port 5000.
