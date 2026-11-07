"""G5.54: create a simple local SVG graphic; no generative AI is implied."""
ACTION_ID = "generate_image"
DESCRIPTION = "Create a local SVG graphic from a short text prompt without using a cloud service."

def run():
    from pathlib import Path
    from datetime import datetime
    import html
    prompt = ACTION_ARGUMENTS.strip() or "WEBSTER"
    label = html.escape(prompt[:120])
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">
<defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#071426"/><stop offset="1" stop-color="#24134b"/></linearGradient></defs>
<rect width="1200" height="675" fill="url(#g)"/><circle cx="600" cy="285" r="170" fill="none" stroke="#22d3ee" stroke-width="4" opacity=".8"/>
<circle cx="600" cy="285" r="135" fill="none" stroke="#a78bfa" stroke-width="2"/><text x="600" y="530" text-anchor="middle" fill="#d8f7ff" font-size="38" font-family="Arial">{label}</text>
<text x="600" y="590" text-anchor="middle" fill="#7dd3fc" font-size="18" font-family="Arial">CREATED LOCALLY BY WEBSTER</text></svg>'''
    folder = Path.home() / "Pictures" / "WEBSTER"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ("graphic_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".svg")
    target.write_text(svg, encoding="utf-8")
    return f"Created a simple SVG graphic locally (not an AI-generated image): {target}"
