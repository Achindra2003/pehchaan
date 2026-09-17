from __future__ import annotations

from dataclasses import dataclass, field

Box = tuple[float, float, float, float]  # left, top, right, bottom, normalised 0-1


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    box: Box

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]


@dataclass
class OcrResult:
    lines: list[OcrLine]
    provider: str
    queries: dict[str, OcrLine] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)
