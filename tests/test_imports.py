import os
from pathlib import Path
import subprocess
import sys


IMPORT_PROBE = """
import socket
import dotenv
import langchain_openai
import tavily
from app.tools import resume_reader

def forbidden(*args, **kwargs):
    raise AssertionError('Import attempted provider construction, network, or user-file read')

langchain_openai.ChatOpenAI = forbidden
tavily.TavilyClient = forbidden
dotenv.load_dotenv = forbidden
resume_reader.read_docx_resume = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.getaddrinfo = forbidden

import app.nodes
import main
import scripts.manual.jooble
import scripts.manual.resume
import scripts.manual.job_sources
assert app.nodes.get_model.cache_info().currsize == 0
assert app.nodes.get_structured_model.cache_info().currsize == 0
print('PASS: credential-free imports; no provider construction, network, or resume/dotenv reads')
"""


def test_fresh_imports_without_credentials():
    environment = {
        key: value for key, value in os.environ.items()
        if not key.endswith("API_KEY")
        and not key.startswith(("OPENAI_", "AZURE_OPENAI_"))
    }
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_PROBE],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "PASS: credential-free imports; no provider construction, network, "
        "or resume/dotenv reads\n"
    )
