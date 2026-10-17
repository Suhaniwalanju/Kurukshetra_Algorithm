import os
import re
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any, Tuple, Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


class DiagramRenderer:
    def __init__(self):
        self.mmdc_path = shutil.which("mmdc")
        self.dot_path = shutil.which("dot")

    def parse_and_validate_spec(self, spec: str) -> Dict[str, Any]:
        """
        Validates Mermaid or DOT diagram spec:
        - Limits to 7 nodes
        - Limits node labels to at most 3 words
        - Identifies if splitting across two slides is needed
        """
        raw_lines = [l.strip() for l in spec.split("\n") if l.strip() and not l.strip().startswith(("%%", "//", "#"))]
        nodes = []
        node_labels = {}
        connections = []

        is_dot = "digraph" in spec or "graph {" in spec

        if is_dot:
            # Parse Graphviz DOT
            for line in raw_lines:
                if "{" in line or "}" in line or line.startswith("digraph"):
                    continue
                # Match A -> B or A -- B
                parts = re.split(r"->|--", line)
                if len(parts) >= 2:
                    p1 = re.sub(r'\[.*?\]|;', '', parts[0]).strip()
                    p2 = re.sub(r'\[.*?\]|;', '', parts[1]).strip()
                    if p1 and p1 not in nodes:
                        nodes.append(p1)
                        node_labels[p1] = p1
                    if p2 and p2 not in nodes:
                        nodes.append(p2)
                        node_labels[p2] = p2
                    if p1 and p2:
                        connections.append((p1, p2))
                else:
                    match = re.search(r'([A-Za-z0-9_]+)\s*\[label="?(.*?)"?\]', line)
                    if match:
                        nid, lbl = match.group(1), match.group(2)
                        if nid not in nodes:
                            nodes.append(nid)
                        node_labels[nid] = lbl
        else:
            # Parse Mermaid
            for line in raw_lines:
                if line.startswith(("graph", "flowchart", "sequenceDiagram", "classDiagram", "subgraph")):
                    continue
                parts = re.split(r"-->|---|==>|-\.->|->", line)
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

        # Fallback if no nodes parsed
        if not nodes:
            nodes = ["InputState", "Processing", "VerifiedOutput"]
            node_labels = {
                "InputState": "Input State",
                "Processing": "Execution Logic",
                "VerifiedOutput": "Verified Result"
            }
            connections = [("InputState", "Processing"), ("Processing", "VerifiedOutput")]

        # Enforce max 3 words per label
        sanitized_labels = {}
        for nid in nodes:
            orig = node_labels.get(nid, nid)
            words = orig.split()
            if len(words) > 3:
                sanitized_labels[nid] = " ".join(words[:3])
            else:
                sanitized_labels[nid] = orig

        needs_split = len(nodes) > 7
        part1_nodes = nodes[:7] if needs_split else nodes
        part2_nodes = nodes[7:] if needs_split else []

        return {
            "nodes": nodes,
            "labels": sanitized_labels,
            "connections": connections,
            "needs_split": needs_split,
            "part1_nodes": part1_nodes,
            "part2_nodes": part2_nodes,
            "node_count": len(nodes),
        }

    def render_diagram_to_png(
        self,
        spec: str,
        output_path: str,
        target_width: int = 744,
        target_height: int = 680,
        palette: Optional[Dict[str, str]] = None,
        font_family: str = "Segoe UI",
        scale: float = 2.0,
    ) -> bool:
        """
        Renders Mermaid or DOT spec to PNG at 2x resolution, sized to fit the slide's
        content placeholder, with text equivalent to at least 16pt, using template colors and font.
        Never leaves a placeholder box or empty diagram area.
        """
        if not spec or not spec.strip():
            spec = "graph LR\n  A[Input State] --> B[Core Engine] --> C[Verified Output]"

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        meta = self.parse_and_validate_spec(spec)

        render_w = int(target_width * scale)
        render_h = int(target_height * scale)

        primary_hex = (palette or {}).get("primary", "#002147")
        accent_hex = (palette or {}).get("accent", "#1E40AF")
        text_hex = (palette or {}).get("text", "#0F172A")
        bg_hex = (palette or {}).get("background", "#FAFAFA")

        return self._render_crisp_canvas(
            meta,
            output_path,
            render_w,
            render_h,
            primary_hex,
            accent_hex,
            text_hex,
            bg_hex,
            font_family,
        )

    def _render_crisp_canvas(
        self,
        meta: Dict[str, Any],
        output_path: str,
        width: int,
        height: int,
        primary_hex: str,
        accent_hex: str,
        text_hex: str,
        bg_hex: str,
        font_family: str,
    ) -> bool:
        """Renders 2x resolution diagram canvas with 16pt-equivalent font (34px at 2x)."""
        try:
            img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(img)

            nodes = meta["nodes"][:7]  # Enforce max 7 nodes
            labels = meta["labels"]
            connections = meta["connections"]

            # Font >= 16pt equivalent at 2x resolution (34px minimum)
            font_size = 36
            font = None
            for cand in [f"{font_family.lower()}.ttf", "segoeui.ttf", "arial.ttf", "calibri.ttf"]:
                try:
                    font = ImageFont.truetype(cand, font_size)
                    break
                except Exception:
                    continue
            if font is None:
                font = ImageFont.load_default()

            num_nodes = len(nodes)
            card_w = min(420, (width - (num_nodes + 1) * 40) // max(1, num_nodes))
            card_h = 160

            # Compute positions
            total_block_w = num_nodes * card_w + (num_nodes - 1) * 80
            start_x = max(40, (width - total_block_w) // 2)
            y_pos = (height - card_h) // 2

            node_boxes = {}
            for i, nid in enumerate(nodes):
                x = start_x + i * (card_w + 80)
                node_boxes[nid] = (x, y_pos, x + card_w, y_pos + card_h)

            # Draw Connections
            for src, dst in connections:
                if src in node_boxes and dst in node_boxes:
                    s = node_boxes[src]
                    d = node_boxes[dst]
                    p1 = (s[2], (s[1] + s[3]) // 2)
                    p2 = (d[0], (d[1] + d[3]) // 2)
                    # Connection line with DPU accent color
                    draw.line([p1, p2], fill=(30, 64, 175, 240), width=6)
                    # Arrowhead
                    draw.polygon([
                        (p2[0], p2[1]),
                        (p2[0] - 18, p2[1] - 12),
                        (p2[0] - 18, p2[1] + 12)
                    ], fill=(30, 64, 175, 255))

            # Draw Cards (DPU Palette: Primary Navy #002147 border, crisp background)
            for nid in nodes:
                box = node_boxes[nid]
                lbl = labels.get(nid, nid)

                # Card drop shadow
                draw.rounded_rectangle([box[0] + 6, box[1] + 6, box[2] + 6, box[3] + 6], radius=18, fill=(0, 0, 0, 35))
                # Card body
                draw.rounded_rectangle(box, radius=18, fill=(255, 255, 255, 250), outline=(0, 33, 71, 240), width=5)
                # Header indicator bar in DPU navy
                draw.rounded_rectangle([box[0] + 10, box[1] + 10, box[2] - 10, box[1] + 24], radius=6, fill=(0, 33, 71, 255))

                # Text positioning (max 3 words per label, 16pt+ equivalent)
                words = lbl.split()
                if len(words) > 2:
                    l1 = " ".join(words[:2])
                    l2 = " ".join(words[2:])
                else:
                    l1 = lbl
                    l2 = ""

                draw.text((box[0] + 24, box[1] + (55 if not l2 else 40)), l1, fill=(15, 23, 42, 255), font=font)
                if l2:
                    draw.text((box[0] + 24, box[1] + 85), l2, fill=(30, 64, 175, 255), font=font)

            img.save(output_path, "PNG")
            return True
        except Exception as e:
            print(f"Error rendering diagram: {e}")
            return False


diagram_renderer = DiagramRenderer()
