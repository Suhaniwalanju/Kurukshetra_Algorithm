from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator


class SlideCode(BaseModel):
    language: str = Field(default="plaintext", description="Language of code snippet")
    version: Optional[str] = Field(default="", description="Version of language/tool")
    source: str = Field(default="", description="Source code, max 12 lines, max 70 chars per line")
    expected_output: str = Field(default="", description="Expected console or execution output")

    @field_validator("source")
    @classmethod
    def validate_source_lines(cls, v: str) -> str:
        if not v:
            return ""
        lines = v.strip().split("\n")
        if len(lines) > 16:  # gentle margin before error, prompt instructs max 12
            # trim or allow up to 14
            lines = lines[:14]
            return "\n".join(lines)
        return v


class SlideDiagram(BaseModel):
    type: Literal["mermaid", "none"] = "mermaid"
    source: str = Field(default="", description="Mermaid diagram definition or text")


class Slide(BaseModel):
    id: int = Field(..., description="Slide sequential identifier")
    type: Literal["cover", "agenda", "concept", "code", "diagram", "exercise", "summary", "closing"] = Field(
        ..., description="Slide category"
    )
    title: str = Field(..., description="Slide title, max 8 words")
    bullets: List[str] = Field(default_factory=list, description="Bullet points, max 5 bullets, max 8 words each")
    code: Optional[SlideCode] = None
    code_ref: Optional[str] = Field(default="", description="Code reference linking to complete runnable example file")
    diagram: Optional[SlideDiagram] = None
    exercise_ref: Optional[str] = Field(default="", description="Optional reference id or brief exercise instruction")
    speaker_hint: Optional[str] = Field(default="", description="Single line speaker note")
    verification_badge: Optional[str] = Field(default=None, description="Small badge: Verified ✔ Ran on <tech+version> · <date>")
    imports_omitted: Optional[bool] = Field(default=False, description="Whether imports were omitted on the slide and code was wrapped")
    imports_omitted_note: Optional[str] = Field(default="", description="Note indicating imports omitted")
    trainer_notes: Optional[str] = Field(default="", description="Full runnable code and notes for trainer")
    notes: Optional[Dict[str, Any]] = Field(default=None, description="Per-slide notes JSON")

    @field_validator("title")
    @classmethod
    def validate_title_words(cls, v: str) -> str:
        words = v.strip().split()
        if len(words) > 8:
            return " ".join(words[:8])
        return v

    @field_validator("bullets")
    @classmethod
    def validate_bullets(cls, v: List[str]) -> List[str]:
        cleaned = []
        for bullet in v[:5]:  # max 5 bullets
            words = bullet.strip().split()
            if len(words) > 8:
                cleaned.append(" ".join(words[:8]))
            else:
                cleaned.append(bullet.strip())
        return cleaned


class DeckSchema(BaseModel):
    topic: str
    college: str
    professor_name: str
    tech_stack: str
    student_level: str
    slides: List[Slide]


class DeckCreateRequest(BaseModel):
    college: str = Field(..., min_length=1, description="College name corresponding to template")
    professor_name: str = Field(..., min_length=1, description="Professor full name")
    topic: str = Field(..., min_length=2, description="Coding topic title")
    student_level: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"
    session_length: int = Field(..., ge=5, le=180, description="Duration in minutes (5 to 180)")
    tech: str = Field(..., min_length=1, description="Primary technology")
    tech_version: Optional[str] = Field(default="", description="Technology version e.g. 21, 3.12")
    include_own_imports: bool = Field(default=True, description="When true, slide generation prompt requires model to include its own imports")


class BoundingBox(BaseModel):
    left: int = Field(..., description="X coordinate in pixels relative to 1920x1080")
    top: int = Field(..., description="Y coordinate in pixels relative to 1920x1080")
    width: int = Field(..., description="Width in pixels")
    height: int = Field(..., description="Height in pixels")

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


class TemplateColors(BaseModel):
    primary: str = "#3E78C8"
    secondary: str = "#243B5A"
    text: str = "#1A1A1A"
    background: str = "#FFFFFF"
    code_bg: str = "#1E1E2E"
    code_text: str = "#F8F8F2"
    muted: str = "#64748B"


class TemplateFonts(BaseModel):
    title: str = "Arial"
    body: str = "Segoe UI"
    code: str = "Consolas"


class TemplateLayoutConfig(BaseModel):
    college: str
    slide_width: int = 1920
    slide_height: int = 1080
    aspect_ratio: str = "16:9"
    template_image_path: str
    template_pptx_path: Optional[str] = None
    logo_path: Optional[str] = None
    style_guide_path: Optional[str] = None
    footer_text: Optional[str] = None
    title_zone: BoundingBox
    content_zone: BoundingBox
    code_zone: BoundingBox
    diagram_zone: BoundingBox
    footer_zone: BoundingBox
    presented_by_zone: BoundingBox
    colors: TemplateColors = Field(default_factory=TemplateColors)
    fonts: TemplateFonts = Field(default_factory=TemplateFonts)
