# Draken - AutoGen Studio Docker Project

A containerized AutoGen Studio setup following Docker best practices.

## Quick Start

1. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

2. **Build and run with Docker Compose:**
   ```bash
   docker-compose up -d
   ```

3. **Access AutoGen Studio:**
   Open your browser to `http://localhost:8081`

## Manual Docker Commands

**Build the image:**
```bash
docker build -t draken-autogenstudio .
```

**Run the container:**
```bash
docker run -d \
  --name draken-autogenstudio \
  -p 8081:8081 \
  -e OPENAI_API_KEY=your_key_here \
  -v autogenstudio-data:/app/.autogenstudio \
  draken-autogenstudio
```

## Docker Best Practices Implemented

✅ **Multi-stage builds** - Smaller final image, faster builds  
✅ **Non-root user** - Enhanced security  
✅ **Layer caching** - Optimized build times  
✅ **Health checks** - Container health monitoring  
✅ **Read-only filesystem** - Security hardening  
✅ **Resource limits** - Prevent resource exhaustion  
✅ **.dockerignore** - Exclude unnecessary files  
✅ **Security options** - No new privileges, security opts  
✅ **Volume persistence** - Data survives container restarts  
✅ **Environment variables** - Configuration management  

## Project Structure

```
Draken/
├── Dockerfile              # Multi-stage optimized Dockerfile
├── docker-compose.yml      # Orchestration configuration
├── requirements.txt        # Python dependencies
├── .dockerignore          # Files to exclude from build
├── .gitignore             # Git ignore patterns
├── .env.example           # Environment variables template
└── README.md              # This file
```

## Maintenance

**View logs:**
```bash
docker-compose logs -f
```

**Stop services:**
```bash
docker-compose down
```

**Rebuild after changes:**
```bash
docker-compose up -d --build
```

**Clean up:**
```bash
docker-compose down -v  # Warning: removes volumes
```

## Configuration

Edit `docker-compose.yml` to adjust:
- Port mappings
- Resource limits (CPU/memory)
- Environment variables
- Volume mounts

## Troubleshooting

**Container won't start:**
- Check logs: `docker-compose logs autogenstudio`
- Verify API keys in `.env` file
- Ensure port 8081 is available

**Permission issues:**
- Container runs as non-root user (UID 1000)
- Ensure volume permissions are correct

## Security Notes

- Never commit `.env` file with real API keys
- Use secrets management for production
- Regularly update base images and dependencies
- Run container with least privileges

## License

MIT
