
"""
Entrypoint for platforms that start the container with:
    python /app/run.py
Boots FastAPI app at app.main:app and binds to the platform PORT.
"""
import os
import uvicorn

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8000'))
    uvicorn.run('app.main:app', host='0.0.0.0', port=port, log_level='info')
