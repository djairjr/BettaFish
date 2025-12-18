"""Chapter JSON placement and list management.

Each chapter will be written to the raw file immediately during streaming generation, and then written after verification is completed.
Formatted chapter.json, and record metadata in the manifest to facilitate subsequent binding."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional


@dataclass
class ChapterRecord:
    """Chapter metadata recorded in the manifest.

    This structure is used to track each chapter's status, file location,
    And a list of possible errors for easy reading by front-end or debugging tools."""

    chapter_id: str
    slug: str
    title: str
    order: int
    status: str
    files: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, object]:
        """Convert records into a serialized dictionary for easy writing to manifest.json"""
        return {
            "chapterId": self.chapter_id,
            "slug": self.slug,
            "title": self.title,
            "order": self.order,
            "status": self.status,
            "files": self.files,
            "errors": self.errors,
            "updatedAt": self.updated_at,
        }


class ChapterStorage:
    """Chapter JSON writing with manifest manager.

    Responsible for:
        - Create an independent run directory and manifest snapshot for each report;
        - Write `stream.raw` on the fly when chapter streaming is generated;
        - After passing the verification, persist `chapter.json` and update the manifest status."""

    def __init__(self, base_dir: str):
        """Create chapter memory.

        Args:
            base_dir: root path of all output run directories"""
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._manifests: Dict[str, Dict[str, object]] = {}

    # ======== Sessions and Lists ========

    def start_session(self, report_id: str, metadata: Dict[str, object]) -> Path:
        """Create an independent chapter output directory and manifest for this report.

        At the same time, the global metadata is written into `manifest.json` for rendering/debugging query.

        Parameters:
            report_id: task ID.
            metadata: Report metadata (title, topic, etc.).

        Return:
            Path: The newly created run directory."""
        run_dir = self.base_dir / report_id
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "reportId": report_id,
            "createdAt": datetime.utcnow().isoformat() + "Z",
            "metadata": metadata,
            "chapters": [],
        }
        self._manifests[self._key(run_dir)] = manifest
        self._write_manifest(run_dir, manifest)
        return run_dir

    def begin_chapter(self, run_dir: Path, chapter_meta: Dict[str, object]) -> Path:
        """Create a chapter subdirectory and mark it as streaming in the manifest.

        An `order-slug` style subdirectory will be generated and the raw file path will be registered in advance.

        Parameters:
            run_dir: session root directory.
            chapter_meta: Contains metadata of chapterId/title/slug/order.

        Return:
            Path: Chapter directory."""
        slug_value = str(
            chapter_meta.get("slug") or chapter_meta.get("chapterId") or "section"
        )
        chapter_dir = self._chapter_dir(
            run_dir,
            slug_value,
            int(chapter_meta.get("order", 0)),
        )
        record = ChapterRecord(
            chapter_id=str(chapter_meta.get("chapterId")),
            slug=slug_value,
            title=str(chapter_meta.get("title")),
            order=int(chapter_meta.get("order", 0)),
            status="streaming",
            files={"raw": str(self._raw_stream_path(chapter_dir).relative_to(run_dir))},
        )
        self._upsert_record(run_dir, record)
        return chapter_dir

    def persist_chapter(
        self,
        run_dir: Path,
        chapter_meta: Dict[str, object],
        payload: Dict[str, object],
        errors: Optional[List[str]] = None,
    ) -> Path:
        """After the chapter streaming is generated, the final JSON is written and the manifest status is updated.

        If the verification fails, the error message will be written to the manifest for front-end display.

        Parameters:
            run_dir: session root directory.
            chapter_meta: Chapter meta information.
            payload: JSON of the chapter that passed the verification.
            errors: Optional error list used to mark invalid status.

        Return:
            Path: The final `chapter.json` file path."""
        slug_value = str(
            chapter_meta.get("slug") or chapter_meta.get("chapterId") or "section"
        )
        chapter_dir = self._chapter_dir(
            run_dir,
            slug_value,
            int(chapter_meta.get("order", 0)),
        )
        final_path = chapter_dir / "chapter.json"
        final_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        record = ChapterRecord(
            chapter_id=str(chapter_meta.get("chapterId")),
            slug=slug_value,
            title=str(chapter_meta.get("title")),
            order=int(chapter_meta.get("order", 0)),
            status="ready" if not errors else "invalid",
            files={
                "raw": str(self._raw_stream_path(chapter_dir).relative_to(run_dir)),
                "json": str(final_path.relative_to(run_dir)),
            },
            errors=errors or [],
        )
        self._upsert_record(run_dir, record)
        return final_path

    def load_chapters(self, run_dir: Path) -> List[Dict[str, object]]:
        """Read all chapters.json from the specified run directory and return them in order.

        Commonly used in DocumentComposer to bind multiple chapters into an entire IR.

        Parameters:
            run_dir: session root directory.

        Return:
            list[dict]: Chapter payload list."""
        payloads: List[Dict[str, object]] = []
        for child in sorted(run_dir.iterdir()):
            if not child.is_dir():
                continue
            chapter_path = child / "chapter.json"
            if not chapter_path.exists():
                continue
            try:
                payload = json.loads(chapter_path.read_text(encoding="utf-8"))
                payloads.append(payload)
            except json.JSONDecodeError:
                continue
        payloads.sort(key=lambda x: x.get("order", 0))
        return payloads

    # ======== File operations ========

    @contextmanager
    def capture_stream(self, chapter_dir: Path) -> Generator:
        """Write streaming output to raw files in real time.

        Expose file handles through contextmanager to simplify the writing logic of chapter nodes.

        Parameters:
            chapter_dir: current chapter directory.

        Return:
            Generator[TextIO]: File object used as a context manager."""
        raw_path = self._raw_stream_path(chapter_dir)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("w", encoding="utf-8") as fp:
            yield fp

    # ======== Internal Tools ========

    def _chapter_dir(self, run_dir: Path, slug: str, order: int) -> Path:
        """Generate a stable directory based on slug/order to ensure that each chapter is saved separately and can be sorted."""
        safe_slug = self._safe_slug(slug)
        folder = f"{order:03d}-{safe_slug}"
        path = run_dir / folder
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _safe_slug(self, slug: str) -> str:
        """Remove dangerous characters to avoid generating illegal folder names."""
        slug = slug.replace(" ", "-").replace("/", "-")
        return slug or "section"

    def _raw_stream_path(self, chapter_dir: Path) -> Path:
        """Returns the raw file path corresponding to the streaming output of a certain chapter."""
        return chapter_dir / "stream.raw"

    def _key(self, run_dir: Path) -> str:
        """Parse the run directory into dictionary cache keys to avoid repeated disk reads."""
        return str(run_dir.resolve())

    def _manifest_path(self, run_dir: Path) -> Path:
        """Get the actual file path of manifest.json."""
        return run_dir / "manifest.json"

    def _write_manifest(self, run_dir: Path, manifest: Dict[str, object]):
        """Write the entire manifest snapshot in memory back to disk."""
        self._manifest_path(run_dir).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_manifest(self, run_dir: Path) -> Dict[str, object]:
        """Read the existing manifest from disk.

        It can be used to restore the context when the process is restarted or when multiple instances write to disk."""
        manifest_path = self._manifest_path(run_dir)
        if manifest_path.exists():
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        return {"reportId": run_dir.name, "chapters": []}

    def _upsert_record(self, run_dir: Path, record: ChapterRecord):
        """Update or append chapter records in the manifest to ensure consistent order.

        Internally it is automatically sorted and written back to cache + disk."""
        key = self._key(run_dir)
        manifest = self._manifests.get(key) or self._read_manifest(run_dir)
        chapters: List[Dict[str, object]] = manifest.get("chapters", [])
        chapters = [c for c in chapters if c.get("chapterId") != record.chapter_id]
        chapters.append(record.to_dict())
        chapters.sort(key=lambda x: x.get("order", 0))
        manifest["chapters"] = chapters
        manifest.setdefault("updatedAt", datetime.utcnow().isoformat() + "Z")
        self._manifests[key] = manifest
        self._write_manifest(run_dir, manifest)


__all__ = ["ChapterStorage", "ChapterRecord"]
