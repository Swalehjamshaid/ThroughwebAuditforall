[build]
builder = "docker"
dockerfilePath = "Dockerfile"

[deploy]
restartPolicyType = "ON_FAILURE"
# This tells Railway to use the dynamic port number
startCommand = "uvicorn backend.main:app --host 0.0.0.0 --port $PORT"
