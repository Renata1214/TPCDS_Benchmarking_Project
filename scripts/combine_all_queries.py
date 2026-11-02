# Example: python3 scripts/combine_all_queries.py

from pathlib import Path
import re


ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT_DIR / "queries" / "all_templates"
OUTPUT_FILE = ROOT_DIR / "queries" / "All_queries_file.txt"
QUERY_FILENAME = re.compile(r"query(\d+)\.sql", re.IGNORECASE)


def main():
    templates = []
    for path in TEMPLATE_DIR.iterdir():
        match = QUERY_FILENAME.fullmatch(path.name)
        if path.is_file() and match:
            templates.append((int(match.group(1)), path))

    templates.sort(key=lambda item: (item[0], item[1].name.lower()))
    if not templates:
        raise FileNotFoundError(f"No query<number>.sql files found in {TEMPLATE_DIR}")

    sections = []
    for number, path in templates:
        sql = path.read_text(encoding="utf-8-sig").strip()
        if not sql:
            raise ValueError(f"Query template is empty: {path}")
        sections.append(f"Query {number}\n\n{sql}")

    with OUTPUT_FILE.open("w", encoding="utf-8", newline="\n") as output:
        output.write("\n\n".join(sections))
        output.write("\n")

    print(f"Wrote {len(sections)} queries to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
