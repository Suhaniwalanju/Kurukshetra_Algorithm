import os
import re
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont
from typing import Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


class DiagramRenderer:
    def __init__(self):
        self.mmdc_path = shutil.which("mmdc")

    def render_mermaid(self, mermaid_code: str, output_path: str, width: int = 800, height: int = 600) -> bool:
        """
        Renders Mermaid code into a high-res PNG at output_path.
        Uses mmdc if available, otherwise generates a clean native vector diagram.
        """
        if not mermaid_code or not mermaid_code.strip():
            return False

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 1. Try mmdc if available
        if self.mmdc_path:
            try:
                temp_mmd = output_path + ".mmd"
                with open(temp_mmd, "w", encoding="utf-8") as f:
                    f.write(mermaid_code)
                res = subprocess.run(
                    [self.mmdc_path, "-i", temp_mmd, "-o", output_path, "-b", "transparent", "-w", str(width)],
                    capture_output=True,
                    timeout=10,
                )
                if os.path.exists(temp_mmd):
                    os.remove(temp_mmd)
                if res.returncode == 0 and os.path.exists(output_path):
                    return True
            except Exception as e:
                print(f"mmdc execution error: {e}")

        # 2. Native clean architectural diagram generator
        return self._render_native_diagram(mermaid_code, output_path, width, height)

    def _render_native_diagram(self, mermaid_code: str, output_path: str, width: int = 800, height: int = 600) -> bool:
        """
        Parses Mermaid flowchart/graph and renders a modern, high-res dark/light diagram.
        """
        try:
            img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(img)

            # Extract nodes and connections from mermaid
            lines = [l.strip() for l in mermaid_code.split("\n") if l.strip() and not l.strip().startswith("%%")]
            
            # Extract connections like A["Label"] --> B["Label"] or A --> B
            nodes = []
            node_labels = {}
            connections = []

            for line in lines:
                if line.startswith(("graph", "flowchart", "sequenceDiagram", "classDiagram")):
                    continue
                # Match patterns like: A[Text] --> B[Text] or A --> B
                parts = re.split(r"-->|---|==>|-\.->", line)
                if len(parts) >= 2:
                    clean_parts = []
                    for p in parts:
                        match = re.search(r'([A-Za-z0-9_]+)(?:\["?(.*?)"?\]|\("?(.*?)"?\)|\{"?(.*?)"?\})?', p.strip())
                        if match:
                            nid = match.group(1)
                            label = match.group(2) or match.group(3) or match.group(4) or nid
                            if nid not in nodes:
                                nodes.append(nid)
                            node_labels[nid] = label.strip()
                            clean_parts.append(nid)
                    if len(clean_parts) >= 2:
                        for i in range(len(clean_parts) - 1):
                            connections.append((clean_parts[i], clean_parts[i + 1]))
                else:
                    match = re.search(r'([A-Za-z0-9_]+)(?:\["?(.*?)"?\]|\("?(.*?)"?\)|\{"?(.*?)"?\})?', line)
                    if match:
                        nid = match.group(1)
                        label = match.group(2) or match.group(3) or match.group(4) or nid
                        if nid not in nodes:
                            nodes.append(nid)
                        node_labels[nid] = label.strip()

            if not nodes:
                # Default generic concept cards
                nodes = ["Input", "Processing", "Verified Output"]
                node_labels = {"Input": "Input / State", "Processing": "Execution Logic", "Verified Output": "Verified Result"}
                connections = [("Input", "Processing"), ("Processing", "Verified Output")]

            # Try to load a nice font
            font = None
            for font_name in ["arial.ttf", "segoeui.ttf", "calibri.ttf"]:
                try:
                    font = ImageFont.truetype(font_name, 22)
                    break
                except Exception:
                    continue
            if font is None:
                font = ImageFont.load_default()

            # Layout nodes vertically or horizontally
            num_nodes = len(nodes)
            card_w = min(220, (width - (num_nodes + 1) * 30) // max(1, num_nodes))
            card_h = 90
            
            # Position nodes horizontally across diagram
            node_positions = {}
            start_x = (width - (num_nodes * card_w + (num_nodes - 1) * 50)) // 2
            y_pos = (height - card_h) // 2

            for i, nid in enumerate(nodes):
                x = start_x + i * (card_w + 50)
                node_positions[nid] = (x, y_pos, x + card_w, y_pos + card_h)

            # Draw connections with arrows
            for src, dst in connections:
                if src in node_positions and dst in node_positions:
                    s_box = node_positions[src]
                    d_box = node_positions[dst]
                    p1 = (s_box[2], (s_box[1] + s_box[3]) // 2)
                    p2 = (d_box[0], (d_box[1] + d_box[3]) // 2)
                    # Line
                    draw.line([p1, p2], fill=(99, 102, 241, 230), width=4)
                    # Arrow head
                    arrow_x = p2[0] - 8
                    arrow_y = p2[1]
                    draw.polygon([(p2[0], arrow_y), (arrow_x - 10, arrow_y - 8), (arrow_x - 10, arrow_y + 8)], fill=(99, 102, 241, 255))

            # Draw nodes (modern rounded cards with subtle drop shadows)
            for nid in nodes:
                box = node_positions[nid]
                lbl = node_labels.get(nid, nid)
                
                # Card background (sleek dark/indigo theme)
                draw.rounded_rectangle([box[0] + 3, box[1] + 3, box[2] + 3, box[3] + 3], radius=12, fill=(0, 0, 0, 40))
                draw.rounded_rectangle(box, radius=12, fill=(248, 250, 252, 240), outline=(99, 102, 241, 220), width=3)
                
                # Text inside card
                # Wrap text if long
                words = lbl.split()
                line1 = " ".join(words[:2]) if len(words) > 2 else lbl
                line2 = " ".join(words[2:]) if len(words) > 2 else ""

                draw.text((box[0] + 16, box[1] + (22 if not line2 else 14)), line1, fill=(30, 41, 59, 255), font=font)
                if line2:
                    draw.text((box[0] + 16, box[1] + 44), line2, fill=(71, 85, 105, 255), font=font)

            img.save(output_path, "PNG")
            return True
        except Exception as e:
            print(f"Error in native diagram rendering: {e}")
            return False


diagram_renderer = DiagramRenderer()
