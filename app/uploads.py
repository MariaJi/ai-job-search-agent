"""Bound uploaded archives before handing them to the existing DOCX reader."""

from io import BytesIO
from zipfile import ZIP_STORED, ZipFile

from app.tools.resume_reader import read_docx_resume

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024
MAX_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_ARCHIVE_FILES = 1000
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class UnreadableResume(Exception):
    pass


def extract_uploaded_resume(content: bytes) -> str:
    normalized = BytesIO()
    try:
        if len(content) > MAX_UPLOAD_BYTES:
            raise UnreadableResume
        # Do not hand an untrusted compressed archive to python-docx's unbounded
        # read() calls. Repack bounded member reads into an in-memory stored ZIP.
        with BytesIO(content) as source, ZipFile(source) as archive, ZipFile(normalized, "w", compression=ZIP_STORED) as safe_archive:
            entries = archive.infolist()
            names = archive.namelist()
            if (len(entries) > MAX_ARCHIVE_FILES
                    or len(set(names)) != len(names)
                    or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES
                    or any(entry.flag_bits & 1 for entry in entries)):
                raise UnreadableResume
            if not {"[Content_Types].xml", "word/document.xml"} <= set(names):
                raise UnreadableResume
            total = 0
            for entry in entries:
                with archive.open(entry) as member, safe_archive.open(entry.filename, "w") as destination:
                    while chunk := member.read(64 * 1024):
                        total += len(chunk)
                        if total > MAX_EXPANDED_BYTES:
                            raise UnreadableResume
                        destination.write(chunk)
        normalized.seek(0)
        text = read_docx_resume(normalized)
        if not text.strip():
            raise UnreadableResume
        return text
    except Exception:
        # Neither archive/parser exceptions nor document contents cross the API.
        raise UnreadableResume from None
    finally:
        normalized.close()
