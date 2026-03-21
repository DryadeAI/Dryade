---
title: Troubleshooting
sidebar_position: 8
description: Solutions for common Dryade issues
---

# Troubleshooting

Solutions for common issues when setting up and running Dryade.

## Docker Issues

### Docker Compose fails to start

**Symptoms:** `docker compose up` exits with errors, services fail to start.

**Solutions:**

1. **Check Docker version:** Dryade requires Docker 24+ and Docker Compose v2+.
   ```bash
   docker --version
   docker compose version
   ```

2. **Check port conflicts:** Ensure ports 3000 (frontend), 8080 (backend), and 5432 (PostgreSQL) are not in use.
   ```bash
   # Check for port conflicts
   lsof -i :3000
   lsof -i :8080
   lsof -i :5432
   ```

3. **Check Docker daemon:** Ensure Docker is running.
   ```bash
   docker info
   ```

4. **Clean restart:** Remove old containers and volumes.
   ```bash
   docker compose down -v
   docker compose up -d
   ```

### Container keeps restarting

**Symptoms:** `docker compose ps` shows a service restarting repeatedly.

**Solutions:**

1. Check container logs for the specific error:
   ```bash
   docker compose logs dryade-backend
   ```

2. Common causes:
   - Missing or invalid `DRYADE_JWT_SECRET` in `.env`
   - Database connection failure (PostgreSQL not ready yet -- wait and retry)
   - Port already in use

## LLM Connection Issues

### "Cannot connect to LLM" or "Connection refused"

**Symptoms:** Chat returns an error about LLM connectivity, or `/health/detailed` shows LLM as unhealthy.

**Solutions:**

1. **Verify your LLM provider is running:**
   ```bash
   # For Ollama
   curl http://localhost:11434/api/version

   # For vLLM
   curl http://localhost:8000/health

   # For OpenAI
   curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
   ```

2. **Check `DRYADE_LLM_BASE_URL` in `.env`:**
   - For Ollama from Docker: use `http://host.docker.internal:11434/v1`
   - For vLLM from Docker: use `http://vllm:8000/v1` (if in same compose network) or `http://host.docker.internal:8000/v1`
   - For OpenAI: use `https://api.openai.com/v1`

3. **Check API key:** If using a cloud provider, ensure `DRYADE_LLM_API_KEY` is set correctly.

4. **Check network:** If running in Docker, ensure the backend can reach the LLM service. Services in the same `docker-compose.yml` can reference each other by service name.

### "Model not found" errors

**Symptoms:** LLM responds with a model-not-found error.

**Solutions:**

1. Check `DRYADE_LLM_MODEL` matches an available model:
   ```bash
   # List models on Ollama
   ollama list

   # List models on vLLM
   curl http://localhost:8000/v1/models
   ```

2. For vLLM, ensure the model is loaded with `--served-model-name` matching your config.

## Database Issues

### "Database migration error"

**Symptoms:** Backend fails to start with database schema errors.

**Solutions:**

- **SQLite (development):** Delete the database file and restart.
  ```bash
  rm dryade.db
  docker compose restart dryade-backend
  ```

- **PostgreSQL:** Run migrations explicitly.
  ```bash
  docker compose exec dryade-backend alembic upgrade head
  ```

### "Connection refused" to database

**Symptoms:** Backend cannot connect to PostgreSQL.

**Solutions:**

1. Check PostgreSQL is running:
   ```bash
   docker compose ps postgres
   ```

2. Verify `DRYADE_DATABASE_URL` in `.env` matches your PostgreSQL configuration.

3. If using Docker Compose, the database service name should be used as the hostname:
   ```env
   DRYADE_DATABASE_URL=postgresql+psycopg://dryade:password@postgres:5432/dryade
   ```

## Frontend Issues

### Frontend shows blank page

**Symptoms:** Opening http://localhost:3000 shows a white/blank page.

**Solutions:**

1. **Check `VITE_API_URL`:** The frontend needs to know where the backend is.
   ```env
   VITE_API_URL=http://localhost:8080
   ```

2. **Check browser console:** Open developer tools (F12) and check the Console tab for errors.

3. **Check backend is accessible:** Navigate to http://localhost:8080/health in your browser.

4. **CORS issues:** If you see CORS errors in the browser console, verify `DRYADE_CORS_ORIGINS` includes your frontend URL.

### UI not updating after changes

**Symptoms:** Code changes to the frontend are not reflected in the browser.

**Solutions:**

1. Hard refresh: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (macOS)
2. Clear browser cache
3. If running in Docker, rebuild the frontend container:
   ```bash
   docker compose build dryade-frontend
   docker compose up -d dryade-frontend
   ```

## GPU Issues

### "GPU not detected" in vLLM

**Symptoms:** vLLM runs on CPU instead of GPU, or fails to start with GPU errors.

**Solutions:**

1. **Check NVIDIA drivers:**
   ```bash
   nvidia-smi
   ```

2. **Install NVIDIA Container Toolkit:**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install nvidia-container-toolkit
   sudo systemctl restart docker
   ```

3. **Verify Docker GPU access:**
   ```bash
   docker run --gpus all nvidia/cuda:12.0-base nvidia-smi
   ```

4. **Check Compute Capability:** vLLM requires CC >= 7.0 (NVIDIA Volta or newer).

### "CUDA out of memory"

See the [Edge Hardware Guide](edge-hardware.md#troubleshooting) for memory optimization strategies.

## Permission Issues

### "Permission denied" errors

**Symptoms:** File access or Docker socket permission errors.

**Solutions:**

1. **Docker socket:** Add your user to the docker group.
   ```bash
   sudo usermod -aG docker $USER
   # Log out and log back in
   ```

2. **File permissions:** Ensure the data directories are writable by the container user.
   ```bash
   chmod -R 755 ./data
   ```

## Debug Commands

Useful commands for diagnosing issues:

```bash
# View all service logs
docker compose logs -f

# View only backend logs
docker compose logs -f dryade-backend

# Check health endpoint
curl http://localhost:8080/health/detailed | python -m json.tool

# Check running services
docker compose ps

# Access backend shell
docker compose exec dryade-backend bash

# Check database connectivity
docker compose exec dryade-backend python -c "from core.config import get_settings; print(get_settings().database_url)"
```

## Getting Help

- **GitHub Issues:** [github.com/DryadeAI/Dryade/issues](https://github.com/DryadeAI/Dryade/issues)
- **GitHub Discussions:** [github.com/DryadeAI/Dryade/discussions](https://github.com/DryadeAI/Dryade/discussions)
- **Discord:** Join our community on Discord for real-time help
