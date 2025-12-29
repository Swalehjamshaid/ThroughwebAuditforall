
[build]
builder = "RAILPACK"
install = "npm ci"
build   = "npm run build"
# Next.js: use the --port flag so it binds correctly
start   = "npx next start --port $PORT"  # or: "npm start"

[variables]
PORT = "8080"
