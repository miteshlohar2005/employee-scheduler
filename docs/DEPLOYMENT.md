# Deployment preparation

## MongoDB

Use MongoDB Atlas or a managed MongoDB service. Create a database user restricted to the target database and set:

```text
MONGO_URI=<managed MongoDB connection string>
MONGO_DB_NAME=<database name>
ADMIN_USERNAME=<admin user>
ADMIN_PASSWORD=<strong random secret>
CORS_ORIGINS=<exact public frontend origin>
```

After first deployment, run `python -m db.seed_data` and `python -m db.roster_seed` once against the deployed MongoDB database.

## Backend

Suitable targets include Azure Container Apps, Render, Fly.io, or any Docker host.

The backend image is [Dockerfile.backend](../Dockerfile.backend). Configure environment variables and health-check `/stores`.

## Frontend

Suitable targets include Azure Static Web Apps, Netlify, or Vercel. Set `VITE_API_BASE_URL` to the public backend URL at build time.

The frontend image is [Dockerfile.frontend](../Dockerfile.frontend). The nginx container serves the Vite build.

Docker Compose local/public preview:

```powershell
docker compose up --build
```

## Release checklist

- Replace demo/in-memory authentication with OAuth/OIDC or a managed identity provider.
- Restrict CORS to the exact frontend origin.
- Enable HTTPS for both frontend and backend.
- Rotate the database and admin credentials.
- Seed persistent data once.
- Run smoke tests against the deployed `/stores`, `/roster/domain`, and `/roster/generate` endpoints.
- Add application monitoring and database backups.
