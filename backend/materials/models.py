from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class StudentNote(BaseModel):
    slide_id: int
    title: str
    explanation: str
    why_it_matters: str
    verified_code: str = ""
    real_output: str = ""
    common_mistake: str
    word_count: int = 0


class PredictedMistake(BaseModel):
    title: str
    buggy_code: str
    error_message: str
    explanation: str


class ProfessorNote(BaseModel):
    slide_id: int
    title: str
    talking_points: List[str] = Field(default_factory=list)
    timing_minutes: int = 3
    likely_questions: List[Dict[str, str]] = Field(default_factory=list)
    fallback_output: str = ""
    predicted_mistakes: List[PredictedMistake] = Field(default_factory=list)
    notes_json: Optional[Dict[str, Any]] = None


class QuizQuestion(BaseModel):
    id: int
    question_type: str = "mcq"  # "mcq" or "code_prediction"
    question: str
    code_snippet: Optional[str] = None
    options: List[str] = Field(default_factory=list)
    correct_answer: str  # "A", "B", "C", or "D"
    explanation: str
    distractor_explanations: Dict[str, str] = Field(default_factory=dict)
    source_slide_id: int = 1
    slide_id: Optional[int] = None
    exercise_ref: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if self.slide_id is None:
            self.slide_id = self.source_slide_id
        elif self.source_slide_id == 1 and self.slide_id != 1:
            self.source_slide_id = self.slide_id


class SyntaxCard(BaseModel):
    title: str
    syntax: str
    notes: str = ""


class PitfallCard(BaseModel):
    pitfall: str
    prevention: str


class TinyExample(BaseModel):
    title: str
    code: str
    output: str


class CheatSheetData(BaseModel):
    college: str
    topic: str
    tech: str
    tech_version: str
    brand_primary: str = "#1E3A8A"
    brand_secondary: str = "#0D9488"
    key_syntax: List[SyntaxCard] = Field(default_factory=list)
    common_pitfalls: List[PitfallCard] = Field(default_factory=list)
    tiny_example: TinyExample
