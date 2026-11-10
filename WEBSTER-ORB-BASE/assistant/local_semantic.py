"""Optional local semantic matching for WEBSTER actions.

Uses FastEmbed/ONNX only when explicitly enabled and the package is installed.
The first model use may need a one-time model download; after it is cached,
inference is local. No prompts or action code are sent to a cloud service.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Iterable

logger = logging.getLogger(__name__)


class LocalSemanticMatcher:
    """Lazy local embedding matcher with safe fallback when unavailable."""

    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, threshold: float = 0.48, ambiguity_gap: float = 0.045):
        self.threshold = float(threshold)
        self.ambiguity_gap = float(ambiguity_gap)
        self._model = None
        self._failed = False
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self._model is not None

    def _load(self):
        if self._model is not None or self._failed:
            return self._model
        with self._lock:
            if self._model is not None or self._failed:
                return self._model
            try:
                from fastembed import TextEmbedding
                model_name = os.getenv("WEBSTER_SEMANTIC_MODEL", self.DEFAULT_MODEL).strip()
                if not model_name:
                    raise ValueError("WEBSTER_SEMANTIC_MODEL is empty")
                # FastEmbed runs an ONNX model locally. Its first initialization
                # can download model files; subsequent runs use its local cache.
                self._model = TextEmbedding(model_name=model_name)
                logger.info("Local semantic model ready: %s", model_name)
            except Exception as exc:
                self._failed = True
                logger.info("Local semantic matching unavailable; lexical routing remains active: %s", exc)
        return self._model

    @staticmethod
    def _action_text(action: object) -> str:
        action_id = str(getattr(action, "action_id", "")).replace("_", " ")
        description = str(getattr(action, "description", ""))
        return f"User wants to {description.rstrip('.')} (action: {action_id})."

    def match(self, query: str, actions: Iterable[object]):
        """Return (action_id, score, alternatives) or None."""
        model = self._load()
        if model is None:
            return None
        candidates = [
            item for item in actions
            if str(getattr(item, "action_id", "")).strip()
        ]
        if not candidates or not query.strip():
            return None
        try:
            texts = [query.strip()] + [self._action_text(item) for item in candidates]
            vectors = list(model.embed(texts))
            if len(vectors) != len(texts):
                return None
            query_vector = vectors[0]
            scored = []
            for item, vector in zip(candidates, vectors[1:]):
                # FastEmbed returns normalized embeddings for the selected model;
                # cosine is calculated explicitly for model-agnostic behavior.
                denom = (float((query_vector * query_vector).sum()) ** 0.5
                         * float((vector * vector).sum()) ** 0.5)
                score = float((query_vector * vector).sum()) / denom if denom else 0.0
                scored.append((score, str(item.action_id)))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            if not scored or scored[0][0] < self.threshold:
                return None
            alternatives = tuple(
                (action_id, round(score, 3))
                for score, action_id in scored[1:4]
                if score >= self.threshold
            )
            if alternatives and scored[0][0] - alternatives[0][1] < self.ambiguity_gap:
                return ("", round(scored[0][0], 3),
                        ((scored[0][1], round(scored[0][0], 3)),) + alternatives)
            return (scored[0][1], round(scored[0][0], 3), alternatives)
        except Exception as exc:
            logger.warning("Local semantic matching failed; using lexical routing: %s", exc)
            return None
