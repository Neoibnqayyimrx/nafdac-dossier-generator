from setuptools import setup, find_packages

setup(
    name="nafdac-dossier-gen",
    version="0.1.0",
    description="Automated NAFDAC pharmaceutical dossier generator",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "typer[all]",
        "rich",
        "python-docx",
        "pdfplumber",
        "Jinja2",
        "PyYAML",
        "pydantic",
        "spacy",
        "requests",
        "beautifulsoup4",
        "lxml",
        "pandas",
        "openpyxl",
        "anthropic",
        "diff-match-patch",
    ],
    entry_points={
        "console_scripts": [
            "nafdac=cli:app",
        ],
    },
)
