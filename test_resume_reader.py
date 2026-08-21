from app.tools.resume_reader import read_docx_resume

resume_text = read_docx_resume("data/resume.docx")

print(resume_text)