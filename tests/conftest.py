import os
import tempfile

_tmp_dir = tempfile.mkdtemp(prefix="sage-test-")
os.environ.setdefault("DB_PATH", os.path.join(_tmp_dir, "agent.db"))
os.environ.setdefault("WORKSPACE", os.path.join(_tmp_dir, "workspace"))
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("ZHIPU_API_KEY", "")
