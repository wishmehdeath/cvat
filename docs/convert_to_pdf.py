#!/usr/bin/env python3
import os
import re
import subprocess

md_path = "docs/realtime_analytics_architecture.md"
html_path = "docs/realtime_analytics_architecture.html"
pdf_path = "docs/realtime_analytics_architecture.pdf"

with open(md_path, "r", encoding="utf-8") as f:
    content = f.read()

html_body = []
in_code = False
code_buf = []

for line in content.split("\n"):
    if line.startswith("```"):
        if in_code:
            html_body.append(
                '<pre class="code-block"><code>'
                + "\n".join(code_buf)
                + "</code></pre>"
            )
            code_buf = []
            in_code = False
        else:
            in_code = True
        continue

    if in_code:
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        code_buf.append(escaped)
        continue

    if line.startswith("# "):
        html_body.append(f"<h1>{line[2:]}</h1>")
    elif line.startswith("## "):
        html_body.append(f"<h2>{line[3:]}</h2>")
    elif line.startswith("### "):
        html_body.append(f"<h3>{line[4:]}</h3>")
    elif line.startswith("#### "):
        html_body.append(f"<h4>{line[5:]}</h4>")
    elif line.startswith("---"):
        html_body.append("<hr/>")
    elif line.startswith("- "):
        text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line[2:])
        text = re.sub(r"`(.*?)`", r"<code>\1</code>", text)
        html_body.append(f"<li>{text}</li>")
    elif line.strip().startswith("|") and "|" in line.strip()[1:]:
        cells = [c.strip() for c in line.strip().split("|")[1:-1]]
        if all(re.match(r"^:?-+:?$", c) for c in cells):
            continue
        is_th = len(html_body) == 0 or "</table>" in html_body[-1] or not html_body[-1].endswith("</tr>")
        cell_tag = "th" if is_th else "td"
        rendered_cells = "".join(f"<{cell_tag}>{re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', c)}</{cell_tag}>" for c in cells)
        row_html = f"<tr>{rendered_cells}</tr>"
        if is_th:
            html_body.append(f"<table><thead>{row_html}</thead><tbody>")
        else:
            html_body.append(row_html)
    elif line.strip() == "":
        if html_body and html_body[-1].startswith("<tr>"):
            html_body.append("</tbody></table>")
        html_body.append("<br/>")
    else:
        text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
        text = re.sub(r"`(.*?)`", r"<code>\1</code>", text)
        html_body.append(f"<p>{text}</p>")

full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>CVAT Real-Time Analytics Architecture</title>
<style>
  @page {{
    size: A4;
    margin: 16mm 14mm 16mm 14mm;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    color: #24292f;
    line-height: 1.6;
    font-size: 13.5px;
    padding: 10px 15px;
  }}
  h1 {{
    font-size: 22px;
    border-bottom: 2px solid #1890ff;
    padding-bottom: 8px;
    color: #0969da;
    margin-top: 10px;
  }}
  h2 {{
    font-size: 17px;
    border-bottom: 1px solid #d0d7de;
    padding-bottom: 6px;
    margin-top: 22px;
    color: #1f2328;
  }}
  h3 {{
    font-size: 14.5px;
    margin-top: 16px;
    color: #24292f;
  }}
  p, li {{
    color: #24292f;
  }}
  li {{
    margin-left: 20px;
    margin-bottom: 4px;
  }}
  hr {{
    border: none;
    border-top: 1px solid #e1e4e8;
    margin: 18px 0;
  }}
  .code-block {{
    background-color: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 12px;
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 11.5px;
    line-height: 1.45;
    page-break-inside: avoid;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  code {{
    background-color: rgba(175, 184, 193, 0.2);
    padding: 2px 5px;
    border-radius: 4px;
    font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
    font-size: 12px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0;
    page-break-inside: avoid;
    font-size: 13px;
  }}
  th, td {{
    border: 1px solid #d0d7de;
    padding: 8px 12px;
    text-align: left;
  }}
  th {{
    background-color: #f6f8fa;
    font-weight: 600;
  }}
  tr:nth-child(even) {{
    background-color: #fcfcfc;
  }}
</style>
</head>
<body>
{''.join(html_body)}
</body>
</html>"""

with open(html_path, "w", encoding="utf-8") as f:
    f.write(full_html)

print("Generated HTML:", html_path)

abs_html = os.path.abspath(html_path)
abs_pdf = os.path.abspath(pdf_path)

# Try Chrome headless print
chrome_bin = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if os.path.exists(chrome_bin):
    cmd = [
        chrome_bin,
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={abs_pdf}",
        f"file://{abs_html}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and os.path.exists(pdf_path):
        print(f"Successfully generated PDF via Google Chrome: {pdf_path}")
        exit(0)

# Fallback to wkhtmltopdf
if os.path.exists("/usr/local/bin/wkhtmltopdf"):
    cmd = ["/usr/local/bin/wkhtmltopdf", "--enable-local-file-access", abs_html, abs_pdf]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and os.path.exists(pdf_path):
        print(f"Successfully generated PDF via wkhtmltopdf: {pdf_path}")
        exit(0)

print("PDF generation failed.")
exit(1)
