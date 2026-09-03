import json
from pathlib import Path

from app.api_models import JobSearchResponse


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_uses_canonical_schema_valid_fixture():
    source = ROOT / 'frontend/src/api.ts'
    assert "import sample from '../../app/fixtures/demo.json'" in source.read_text()
    fixture = ROOT / 'app/fixtures/demo.json'
    result = JobSearchResponse.model_validate_json(fixture.read_text())
    assert result.run_summary.returned_jobs == len(result.ranked_jobs)
    assert not (ROOT / 'frontend/public/demo.json').exists()


def test_static_host_config_has_no_api_or_auth_and_denies_connections():
    config = json.loads((ROOT / 'frontend/public/staticwebapp.config.json').read_text())
    assert config['navigationFallback']['rewrite'] == '/index.html'
    assert '/api/*' in config['navigationFallback']['exclude']
    assert 'routes' not in config and 'auth' not in config and 'platform' not in config
    headers = config['globalHeaders']
    assert "connect-src 'none'" in headers['Content-Security-Policy']
    assert "form-action 'none'" in headers['Content-Security-Policy']
    assert headers['X-Content-Type-Options'] == 'nosniff'
