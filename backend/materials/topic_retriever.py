import os
import re
from typing import List, Dict, Optional, Tuple, Any


class TopicRetriever:
    """
    Retrieves factual reference chunks from input/Topics/ PDFs for slide notes generation.
    Ensures slide notes are strictly grounded in retrieved topic facts.
    """
    def __init__(self, topics_base_dir: Optional[str] = None):
        self.base_dir = topics_base_dir or os.path.join(os.getcwd(), "input", "Topics")
        self._cache: Dict[str, List[str]] = {}

    def find_topic_folder(self, topic: str, tech: str) -> Optional[str]:
        if not os.path.exists(self.base_dir):
            return None
        dirs = [d for d in os.listdir(self.base_dir) if os.path.isdir(os.path.join(self.base_dir, d))]
        if not dirs:
            return None

        query = f"{tech} {topic}".lower()
        query_words = [w for w in re.findall(r'[a-zA-Z0-9_\+]+', query) if len(w) > 1]

        best_dir = None
        best_score = -1

        for d in dirs:
            d_lower = d.lower()
            score = 0
            for w in query_words:
                if w in d_lower:
                    score += 3
            # Bonus for tech matching
            if tech.lower() in d_lower:
                score += 5
            # Specific mappings
            if "java" in tech.lower() and "java" in d_lower:
                score += 10
            elif "python" in tech.lower() and "python" in d_lower:
                score += 10
            elif "c++" in tech.lower() and "c++" in d_lower:
                score += 10
            elif tech.lower() == "c" and ("c17" in d_lower or "memory" in d_lower):
                score += 10
            elif "mongo" in tech.lower() and "mongo" in d_lower:
                score += 10
            elif "node" in tech.lower() and "node" in d_lower:
                score += 10
            elif "react" in tech.lower() and "react" in d_lower:
                score += 10
            elif "sql" in tech.lower() and ("postgres" in d_lower or "sql" in d_lower):
                score += 10
            elif "tailwind" in tech.lower() and "tailwind" in d_lower:
                score += 10

            if score > best_score:
                best_score = score
                best_dir = os.path.join(self.base_dir, d)

        return best_dir

    def get_topic_chunks(self, topic: str, tech: str) -> List[str]:
        """Loads and splits the topic PDF into text chunks."""
        folder = self.find_topic_folder(topic, tech)
        if not folder or not os.path.exists(folder):
            return []

        if folder in self._cache:
            return self._cache[folder]

        chunks = []
        try:
            import pypdf
            pdf_files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
            for pdf_file in pdf_files:
                pdf_path = os.path.join(folder, pdf_file)
                reader = pypdf.PdfReader(pdf_path)
                for page_idx, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    paras = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
                    if paras:
                        chunks.extend(paras)
                    elif len(text.strip()) > 50:
                        chunks.append(text.strip())
        except Exception as e:
            print(f"Error extracting topic chunks from {folder}: {e}")

        self._cache[folder] = chunks
        return chunks

    def retrieve_chunks_for_slide(
        self,
        slide: Dict[str, Any],
        topic: str,
        tech: str,
        top_k: int = 4,
    ) -> List[str]:
        """
        Retrieves top-k factual chunks relevant to the specific slide content.
        Uses keyword overlap scoring.
        """
        all_chunks = self.get_topic_chunks(topic, tech)
        if not all_chunks:
            return []

        title = slide.get("title", "")
        bullets = slide.get("bullets", [])
        code = ""
        c = slide.get("code")
        if isinstance(c, dict):
            code = c.get("source", "")
        elif isinstance(c, str):
            code = c

        slide_text = f"{title} {' '.join(bullets)} {code}".lower()
        slide_tokens = set(re.findall(r'[a-zA-Z0-9_]{3,}', slide_text))

        stopwords = {
            "the", "and", "for", "with", "from", "that", "this", "what", "which",
            "your", "will", "have", "been", "about", "into", "over", "after"
        }
        slide_keywords = [t for t in slide_tokens if t not in stopwords]

        scored_chunks: List[Tuple[float, str]] = []
        for chunk in all_chunks:
            chunk_lower = chunk.lower()
            score = sum(1 for kw in slide_keywords if kw in chunk_lower)
            if score > 0:
                scored_chunks.append((score, chunk))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        if scored_chunks:
            return [c for _, c in scored_chunks[:top_k]]
        return all_chunks[:top_k]


topic_retriever = TopicRetriever()
