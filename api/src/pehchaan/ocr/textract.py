"""Amazon Textract: parse Hackingly's existing response, or call Textract directly."""

from __future__ import annotations

from typing import Any

from pehchaan.ocr.base import Box, OcrLine, OcrResult

QUERIES: dict[str, str] = {
    "NAME": "What is the full name of the card holder?",
    "DOB": "What is the date of birth?",
    "ID_NUMBER": "What is the ID card number?",
    "INSTITUTION": "What is the name of the college, university or school?",
    "VALID_UNTIL": "Until what date is the card valid?",
}


def parse_textract(response: dict[str, Any], provider: str = "textract") -> OcrResult:
    blocks = response.get("Blocks") or []
    by_id = {block["Id"]: block for block in blocks if "Id" in block}
    lines = [
        OcrLine(block["Text"], block.get("Confidence", 0.0) / 100, _box(block))
        for block in blocks
        if block.get("BlockType") == "LINE" and block.get("Text")
    ]
    lines.sort(key=lambda line: (round(line.box[1], 2), line.box[0]))

    queries: dict[str, OcrLine] = {}
    for block in blocks:
        if block.get("BlockType") != "QUERY":
            continue
        alias = (block.get("Query") or {}).get("Alias")
        answers = [
            by_id[answer_id]
            for relation in block.get("Relationships") or []
            if relation.get("Type") == "ANSWER"
            for answer_id in relation.get("Ids", [])
            if answer_id in by_id
        ]
        if alias and answers and answers[0].get("Text"):
            answer = answers[0]
            queries[alias] = OcrLine(answer["Text"], answer.get("Confidence", 0.0) / 100, _box(answer))
    return OcrResult(lines=lines, provider=provider, queries=queries)


def _box(block: dict[str, Any]) -> Box:
    bb = (block.get("Geometry") or {}).get("BoundingBox") or {}
    left, top = bb.get("Left", 0.0), bb.get("Top", 0.0)
    return (left, top, left + bb.get("Width", 0.0), top + bb.get("Height", 0.0))


class TextractClient:
    def __init__(self, region: str) -> None:
        import boto3

        self._client = boto3.client("textract", region_name=region)

    def detect(self, jpeg: bytes) -> OcrResult:
        return parse_textract(self._client.detect_document_text(Document={"Bytes": jpeg}))

    def query(self, jpeg: bytes, aliases: list[str]) -> dict[str, OcrLine]:
        queries = [{"Text": QUERIES[alias], "Alias": alias} for alias in aliases if alias in QUERIES]
        if not queries:
            return {}
        response = self._client.analyze_document(
            Document={"Bytes": jpeg}, FeatureTypes=["QUERIES"], QueriesConfig={"Queries": queries}
        )
        return parse_textract(response).queries
