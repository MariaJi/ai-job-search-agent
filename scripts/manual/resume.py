"""Explicit local DOCX text diagnostic; no bundled resume or default path."""


def main():
    import argparse
    from app.tools.resume_reader import read_docx_resume

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to a DOCX resume you choose to inspect")
    args = parser.parse_args()
    print(read_docx_resume(args.path))


if __name__ == "__main__":
    main()
