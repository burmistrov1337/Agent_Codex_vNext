"""Generate PDF from markdown architecture document."""
import re
from fpdf import FPDF


class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, 'ADK Cosmetics / SaveYourHair - Max Bot Architecture', align='R')
        self.ln(5)
        self.set_draw_color(0, 100, 180)
        self.line(10, 15, 200, 15)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, 'Str. {}'.format(self.page_no()), align='C')

    def chapter_title(self, txt):
        self.set_font('Arial', 'B', 14)
        self.set_text_color(0, 70, 140)
        self.ln(4)
        self.cell(0, 10, txt, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 100, 180)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def section_title(self, txt):
        self.set_font('Arial', 'B', 11)
        self.set_text_color(50, 50, 50)
        self.ln(2)
        self.cell(0, 8, txt, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def sub_section_title(self, txt):
        self.set_font('Arial', 'B', 10)
        self.set_text_color(60, 60, 60)
        self.ln(2)
        self.cell(0, 7, txt, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def sub_sub_title(self, txt):
        self.set_font('Arial', 'B', 9)
        self.set_text_color(80, 80, 80)
        self.ln(1)
        self.cell(0, 6, txt, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, txt):
        self.set_font('Arial', '', 9)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 6, txt)
        self.ln(2)

    def bold_line(self, txt):
        self.set_font('Arial', 'B', 9)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 6, txt)
        self.ln(1)

    def bullet_point(self, txt, indent=10):
        self.set_font('Arial', '', 9)
        self.set_text_color(30, 30, 30)
        x = self.get_x()
        self.set_x(x + indent)
        self.cell(5, 6, '\u2022')
        self.multi_cell(0, 6, txt)
        self.ln(1)

    def code_block(self, txt):
        self.set_fill_color(240, 240, 245)
        self.set_font('Arial', '', 7)
        self.set_text_color(0, 80, 0)
        lines = txt.strip().split('\n')
        total_h = len(lines) * 5 + 4
        if self.get_y() + total_h > 280:
            self.add_page()
        self.rect(10, self.get_y(), 190, total_h, 'DF')
        self.set_x(13)
        self.set_y(self.get_y() + 2)
        for line in lines:
            self.cell(0, 5, line[:100], new_x="LMARGIN", new_y="NEXT")
        self.ln(4)


def generate_pdf():
    with open('docs/max_bot_architecture.md', 'r', encoding='utf-8') as f:
        md_content = f.read()

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.add_font('Arial', '', r'C:\Windows\Fonts\arial.ttf', uni=True)
    pdf.add_font('Arial', 'B', r'C:\Windows\Fonts\arialbd.ttf', uni=True)
    pdf.add_font('Arial', 'I', r'C:\Windows\Fonts\ariali.ttf', uni=True)
    pdf.add_font('Arial', 'BI', r'C:\Windows\Fonts\arialbi.ttf', uni=True)

    lines = md_content.split('\n')
    in_code_block = False
    code_text = ""
    in_list = False

    for line in lines:
        if line.strip().startswith('```'):
            if in_code_block:
                pdf.code_block(code_text)
                code_text = ""
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_text += line + '\n'
            continue

        if line.strip().startswith('---'):
            pdf.ln(3)
            continue

        if line.startswith('# '):
            if in_list:
                pdf.ln(2)
                in_list = False
            pdf.chapter_title(line[2:].strip())
        elif line.startswith('## '):
            if in_list:
                pdf.ln(2)
                in_list = False
            pdf.section_title(line[3:].strip())
        elif line.startswith('### '):
            if in_list:
                pdf.ln(2)
                in_list = False
            pdf.sub_section_title(line[4:].strip())
        elif line.startswith('#### '):
            if in_list:
                pdf.ln(2)
                in_list = False
            pdf.sub_sub_title(line[5:].strip())
        elif line.startswith('**') and line.endswith('**'):
            pdf.bold_line(line.strip('**'))
        elif line.strip().startswith('- '):
            in_list = True
            text = line.strip()[2:].replace('**', '')
            pdf.bullet_point(text)
        elif re.match(r'^\d+\.\s', line.strip()):
            in_list = True
            pdf.set_font('Arial', '', 9)
            pdf.set_text_color(30, 30, 30)
            pdf.multi_cell(0, 6, line.strip())
            pdf.ln(1)
        elif line.strip():
            if in_list:
                pdf.ln(2)
                in_list = False
            text = line.strip()
            text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
            text = re.sub(r'\*(.*?)\*', r'\1', text)
            text = re.sub(r'`(.*?)`', r'\1', text)
            pdf.body_text(text)
        else:
            if in_list:
                pdf.ln(1)
            else:
                pdf.ln(2)

    output_path = 'docs/max_bot_architecture.pdf'
    pdf.output(output_path)
    print("PDF generated: {}".format(output_path))


if __name__ == '__main__':
    generate_pdf()
