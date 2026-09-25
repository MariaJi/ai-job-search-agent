import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api_models import JobSearchResponse


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('service', ['app.api', 'public_demo.app'])
def test_demo_semantics_match_budgeted_verification(service, monkeypatch):
    from importlib import import_module
    from app.nodes import select_verification_candidates

    monkeypatch.setenv('ENABLE_LIVE_SEARCH', 'false')
    monkeypatch.setenv('CORS_ORIGINS', '')
    monkeypatch.setenv('MAX_VERIFICATION_JOBS', '2')
    fixture = json.loads((ROOT / 'app/fixtures/demo.json').read_text(encoding='utf-8'))
    with TestClient(import_module(service).create_app()) as client:
        response = client.get('/api/v1/demo')
    assert response.status_code == 200
    assert response.json() == fixture
    result = JobSearchResponse.model_validate(fixture)
    verified, missing, unattempted = result.ranked_jobs
    assert [job.verification_status for job in result.ranked_jobs] == [
        'verified', 'not_found', 'not_attempted',
    ]
    assert verified.analysis_type == 'verified'
    assert verified.preliminary_match_score == 84
    assert verified.verified_match_score == 91
    assert verified.recommendation == 'Apply'
    assert verified.source_urls.description == verified.source_urls.verified
    assert verified.source_urls.verified is not None
    for job in (missing, unattempted):
        assert job.analysis_type == 'preliminary'
        assert job.preliminary_match_score >= 75
        assert job.verified_match_score is None
        assert job.source_urls.verified is None
        assert job.source_urls.description is None
        assert job.recommendation == 'Review original posting'

    # All three scores qualify for at least Medium priority. Only the top two
    # preliminary scores fit this sample's budget, regardless of final scores.
    preliminary = sorted([
        {'title': job.title, 'match_score': job.preliminary_match_score,
         'verification_priority': 'Medium'} for job in result.ranked_jobs
    ], key=lambda job: job['match_score'], reverse=True)
    candidates = select_verification_candidates({'ranked_jobs': preliminary})['verification_candidates']
    attempted = [job for job in result.ranked_jobs if job.verification_status != 'not_attempted']
    assert {job['title'] for job in candidates} == {job.title for job in attempted}
    current_scores = [job.verified_match_score if job.verified_match_score is not None
                      else job.preliminary_match_score for job in result.ranked_jobs]
    assert current_scores == sorted(current_scores, reverse=True)
    summary = result.run_summary
    assert summary.jobs_found == summary.jobs_analyzed == summary.returned_jobs == len(result.ranked_jobs) == 3
    assert summary.verification_attempted == len(attempted) == 2
    assert summary.verified_jobs == sum(job.analysis_type == 'verified' for job in result.ranked_jobs) == 1
    assert summary.preliminary_jobs == sum(job.analysis_type == 'preliminary' for job in result.ranked_jobs) == 2
    assert summary.selected_jobs == sum(
        job.verification_status == 'verified' and job.analysis_type == 'verified'
        and job.recommendation == 'Apply' and job.verified_match_score >= 75
        for job in result.ranked_jobs
    ) == 1
    assert summary.status == 'partial'
    assert any('budget' in warning for warning in summary.warnings)


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
