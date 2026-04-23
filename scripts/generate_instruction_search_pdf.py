from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF


DOC_TITLE = "ADK Cosmetics / Поиск инструкций"
INPUT_PATH = Path("docs/instruction_search_design.md")
OUTPUT_PATH = Path("docs/instruction_search_design.pdf")


class PDF(FPDF):
    def header(self) -> None:
        self.set_font("Arial", "B", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, DOC_TITLE, align="R")
        self.ln(5)
        self.set_draw_color(0, 100, 180)
        self.line(10, 15, 200, 15)
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128)
        self.cell(0, 10, f"Стр. {self.page_no()}", align="C")

    def chapter_title(self, txt: str) -> None:
        self.set_font("Arial", "B", 14)
        self.set_text_color(0, 70, 140)
        self.ln(4)
        self.cell(0, 10, txt, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 100, 180)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def section_title(self, txt: str) -> None:
        self.set_font("Arial", "B", 11)
        self.set_text_color(50, 50, 50)
        self.ln(2)
        self.cell(0, 8, txt, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def sub_section_title(self, txt: str) -> None:
        self.set_font("Arial", "B", 10)
        self.set_text_color(60, 60, 60)
        self.ln(2)
        self.cell(0, 7, txt, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, txt: str) -> None:
        self.set_font("Arial", "", 9)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 6, txt)
        self.ln(2)

    def bullet_point(self, txt: str, indent: int = 10) -> None:
        self.set_font("Arial", "", 9)
        self.set_text_color(30, 30, 30)
        x = self.get_x()
        self.set_x(x + indent)
        self.cell(5, 6, "-")
        self.multi_cell(0, 6, txt)
        self.ln(1)


def _clean_inline_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"`(.*?)`", r"\1", text)
    return text


def generate_pdf() -> Path:
    md_content = INPUT_PATH.read_text(encoding="utf-8")

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_font("Arial", "", r"C:\Windows\Fonts\arial.ttf", uni=True)
    pdf.add_font("Arial", "B", r"C:\Windows\Fonts\arialbd.ttf", uni=True)
    pdf.add_font("Arial", "I", r"C:\Windows\Fonts\ariali.ttf", uni=True)
    pdf.add_font("Arial", "BI", r"C:\Windows\Fonts\arialbi.ttf", uni=True)
    pdf.add_page()

    in_list = False
    for raw_line in md_content.splitlines():
        line = raw_line.rstrip()

        if line.startswith("# "):
            if in_list:
                pdf.ln(2)
                in_list = False
            pdf.chapter_title(_clean_inline_markdown(line[2:].strip()))
        elif line.startswith("## "):
            if in_list:
                pdf.ln(2)
                in_list = False
            pdf.section_title(_clean_inline_markdown(line[3:].strip()))
        elif line.startswith("### "):
            if in_list:
                pdf.ln(2)
                in_list = False
            pdf.sub_section_title(_clean_inline_markdown(line[4:].strip()))
        elif line.strip().startswith("- "):
            in_list = True
            pdf.bullet_point(_clean_inline_markdown(line.strip()[2:]))
        elif re.match(r"^\d+\.\s", line.strip()):
            in_list = True
            pdf.bullet_point(_clean_inline_markdown(re.sub(r"^\d+\.\s*", "", line.strip())))
        elif line.strip():
            if in_list:
                pdf.ln(2)
                in_list = False
            pdf.body_text(_clean_inline_markdown(line.strip()))
        else:
            pdf.ln(2)

    pdf.output(str(OUTPUT_PATH))
    return OUTPUT_PATH


if __name__ == "__main__":
    path = generate_pdf()
    print(f"PDF generated: {path}")
