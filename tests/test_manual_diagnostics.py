import sys
from unittest.mock import Mock

import dotenv
import pytest

from app import nodes
from app.tools import job_search, resume_reader, web_search
from scripts.manual import job_sources, jooble, resume


def test_manual_resume_reads_only_the_explicit_path(monkeypatch, capsys):
    reader = Mock(return_value="Synthetic resume text")
    monkeypatch.setattr(resume_reader, "read_docx_resume", reader)
    monkeypatch.setattr(sys, "argv", ["resume", "synthetic.docx"])
    resume.main()
    reader.assert_called_once_with("synthetic.docx")
    assert capsys.readouterr().out == "Synthetic resume text\n"


def test_manual_jooble_arguments_without_resume_read(monkeypatch, capsys):
    load = Mock()
    search = Mock(return_value={"jobs": []})
    reader = Mock(side_effect=AssertionError("No resume should be read"))
    monkeypatch.setattr(dotenv, "load_dotenv", load)
    monkeypatch.setattr(job_search, "search_jooble_jobs", search)
    monkeypatch.setattr(resume_reader, "read_docx_resume", reader)
    monkeypatch.setattr(sys, "argv", ["jooble", "--keywords", "AI Engineer"])
    jooble.main()
    load.assert_called_once()
    search.assert_called_once_with(keywords="AI Engineer", location="Remote", results_per_page=3)
    reader.assert_not_called()
    assert '"jobs": []' in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["empty", "ranked", "source", "verify"])
def test_manual_source_diagnostics_use_current_interfaces(monkeypatch, capsys, mode):
    posting = {"title": "Engineer", "url": "https://example.com/jobs/1"}
    broad = Mock(return_value=[posting])
    ranking = Mock(return_value=[] if mode == "empty" else [posting])
    source = Mock(return_value=[posting])
    exact = Mock(return_value=posting)
    extract = Mock(return_value={"status": "success", "content": "Synthetic description"})
    verify = Mock(return_value={"verified_jobs": [{"verification_status": "not_found"}]})
    monkeypatch.setattr(dotenv, "load_dotenv", Mock())
    monkeypatch.setattr(web_search, "search_original_job", broad)
    monkeypatch.setattr(nodes, "rank_job_sources", ranking)
    monkeypatch.setattr(web_search, "search_job_on_source", source)
    monkeypatch.setattr(nodes, "select_exact_job_posting", exact)
    monkeypatch.setattr(web_search, "extract_job_description", extract)
    monkeypatch.setattr(nodes, "verify_job", verify)
    argv = ["job_sources", "--title", "Engineer", "--company", "Example"]
    if mode == "source":
        argv.extend(["--source-url", "https://example.com/jobs"])
    elif mode == "verify":
        argv.append("--verify")
    monkeypatch.setattr(sys, "argv", argv)

    job_sources.main()
    output = capsys.readouterr().out
    if mode == "verify":
        verify.assert_called_once()
        broad.assert_not_called()
        assert "not_found" in output
    elif mode == "empty":
        extract.assert_not_called()
        assert "extraction skipped" in output
    else:
        extract.assert_called_once_with(posting["url"])
        assert "Synthetic description" in output
        if mode == "source":
            source.assert_called_once_with(
                title="Engineer", company="Example", source_url="https://example.com/jobs",
            )
            exact.assert_called_once()
