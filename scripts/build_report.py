"""Build the plain monochrome report. Requires reportlab and a Chinese TTF font."""
import argparse
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]


def inline(text):
    text = escape(text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    return re.sub(r'(https://github\.com/mj20050127/Fieldnote)',
                  r'<link href="\1" color="black">\1</link>', text)


def build(source, output, font):
    pdfmetrics.registerFont(TTFont('ReportSong', str(font), subfontIndex=0))
    bold = Path('C:/Windows/Fonts/simhei.ttf')
    pdfmetrics.registerFont(TTFont('ReportBold', str(bold if bold.exists() else font), subfontIndex=0))
    pdfmetrics.registerFontFamily('ReportSong', normal='ReportSong', bold='ReportBold',
                                  italic='ReportSong', boldItalic='ReportBold')
    body = ParagraphStyle('Body', fontName='ReportSong', fontSize=11,
                          leading=18.5, spaceAfter=7, wordWrap='CJK', textColor=colors.black,
                          alignment=TA_LEFT, splitLongWords=True, allowWidows=0, allowOrphans=0)
    styles = {
        'body': body,
        'title': ParagraphStyle('Title', parent=body, fontName='ReportBold', fontSize=17,
                                leading=25, alignment=TA_CENTER, spaceBefore=10, spaceAfter=12),
        'h2': ParagraphStyle('H2', parent=body, fontName='ReportBold', fontSize=14,
                             leading=22, spaceBefore=9, spaceAfter=8, keepWithNext=True),
        'h3': ParagraphStyle('H3', parent=body, fontName='ReportBold', fontSize=11.5,
                             leading=19, spaceBefore=6, spaceAfter=5, keepWithNext=True),
        'table': ParagraphStyle('Cell', parent=body, fontSize=9.2, leading=14.5, spaceAfter=0),
        'code': ParagraphStyle('Code', fontName='Courier', fontSize=8.2, leading=12,
                               textColor=colors.black, spaceBefore=4, spaceAfter=9),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    width = A4[0] - 124
    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=62, leftMargin=62,
                            topMargin=48, bottomMargin=47, title='拾问 Fieldnote 第一阶段项目完成报告',
                            author='Fieldnote', subject='MongoDB 在线问卷系统课程项目完成报告')
    lines = source.read_text(encoding='utf-8-sig').splitlines()
    story, index = [], 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line == '<!-- pagebreak -->':
            story.append(Spacer(1, 5))
            index += 1
            continue
        if line.startswith(('```', '~~~')):
            fence, code = line[:3], []
            index += 1
            while index < len(lines) and not lines[index].startswith(fence):
                code.append(lines[index])
                index += 1
            story.append(Preformatted('\n'.join(code), styles['code'], maxLineLength=91))
            index += 1
            continue
        if line.startswith('|'):
            rows = []
            while index < len(lines) and lines[index].strip().startswith('|'):
                cells = [cell.strip() for cell in lines[index].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', cell) for cell in cells):
                    rows.append([Paragraph(inline(cell), styles['table']) for cell in cells])
                index += 1
            ratios = [0.24, 0.43, 0.33] if len(rows[0]) == 3 else [0.39, 0.61]
            table = Table(rows, colWidths=[width * ratio for ratio in ratios], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.35, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.extend([table, Spacer(1, 9)])
            continue
        level = 'title' if line.startswith('# ') else 'h2' if line.startswith('## ') else 'h3' if line.startswith('### ') else 'body'
        story.append(Paragraph(inline(re.sub(r'^#{1,3} ', '', line)), styles[level]))
        index += 1

    def page_number(canvas, document):
        canvas.saveState()
        canvas.setFillColor(colors.black)
        canvas.setFont('ReportSong', 9)
        canvas.drawCentredString(A4[0] / 2, 25, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'docs/PROJECT_REPORT.md')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/pdf/Fieldnote_第一阶段项目完成报告.pdf')
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/simsun.ttc'))
    args = parser.parse_args()
    if not args.font.is_file():
        parser.error('Provide a Chinese TrueType font with --font.')
    build(args.source, args.output, args.font)
    print(args.output)
