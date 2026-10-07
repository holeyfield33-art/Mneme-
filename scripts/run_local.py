"""Start Mneme exclusively on loopback in explicit offline personal mode."""
import sys
from local_config import ROOT, configure_environment

config = configure_environment()
sys.path.insert(0, str(ROOT / "aletheia-mneme"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=config["service_port"],
                access_log=False, log_level="info", proxy_headers=False)
