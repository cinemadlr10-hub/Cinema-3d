from httpx import Client
from uvicorn import Config, Server
import threading, time

# Simple smoke test using a live server for demonstration purposes
def run_server():
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, log_level="error")

def test_get_movies_endpoint():
    # Start server in background thread
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(1.2)

    with Client() as client:
        r = client.get("http://127.0.0.1:8001/api/peliculas")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
