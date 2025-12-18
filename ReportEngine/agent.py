"""Report Agent main class.

This module connects template selection, layout design, chapter generation, IR binding and HTML rendering, etc.
All sub-processes are the overall dispatch center of Report Engine. Core responsibilities include:
1. Manage input data and status, coordinate three analysis engines, forum logs and templates;
2. Drive template selection in node order→layout generation→length planning→chapter writing→binding rendering;
3. Responsible for error recovery, streaming event distribution, placement list and final result storage."""

import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable, Tuple

from loguru import logger

from .core import (
    ChapterStorage,
    DocumentComposer,
    TemplateSection,
    parse_template_sections,
)
from .ir import IRValidator
from .llms import LLMClient
from .nodes import (
    TemplateSelectionNode,
    ChapterGenerationNode,
    ChapterJsonParseError,
    ChapterContentError,
    ChapterValidationError,
    DocumentLayoutNode,
    WordBudgetNode,
)
from .renderers import HTMLRenderer
from .state import ReportState
from .utils.config import settings, Settings


class StageOutputFormatError(ValueError):
    """A controlled exception thrown when the staged output structure is not as expected."""


class FileCountBaseline:
    """File count benchmark manager.

    This tool is used for:
    - Record the number of Markdown exported by the three engines of Insight/Media/Query when the task is started;
    - Quickly determine whether a new report has landed in subsequent polls;
    - Provide the Flask layer with a basis for "whether the input is ready"."""
    
    def __init__(self):
        """During initialization, priority is given to trying to read existing baseline snapshots.

        If `logs/report_baseline.json` does not exist, an empty snapshot will be automatically created.
        So that subsequent `initialize_baseline` writes the real baseline on first run."""
        self.baseline_file = 'logs/report_baseline.json'
        self.baseline_data = self._load_baseline()
    
    def _load_baseline(self) -> Dict[str, int]:
        """Load benchmark data.

        - Parse JSON directly when the snapshot file exists;
        - Catch all loading exceptions and return an empty dictionary to ensure the caller's logic is simple."""
        try:
            if os.path.exists(self.baseline_file):
                with open(self.baseline_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.exception(f"Failed to load benchmark data: {e}")
        return {}
    
    def _save_baseline(self):
        """Writes the current baseline to disk.

        Use `ensure_ascii=False` + indent format to facilitate manual viewing;
        If the target directory is missing, it will be created automatically."""
        try:
            os.makedirs(os.path.dirname(self.baseline_file), exist_ok=True)
            with open(self.baseline_file, 'w', encoding='utf-8') as f:
                json.dump(self.baseline_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception(f"Failed to save benchmark data: {e}")
    
    def initialize_baseline(self, directories: Dict[str, str]) -> Dict[str, int]:
        """Initialize file number baseline.

        Traverse each engine directory and count the number of `.md` files, and persist the results as
        Initial baseline. Subsequent `check_new_files` will compare the increments accordingly."""
        current_counts = {}
        
        for engine, directory in directories.items():
            if os.path.exists(directory):
                md_files = [f for f in os.listdir(directory) if f.endswith('.md')]
                current_counts[engine] = len(md_files)
            else:
                current_counts[engine] = 0
        
        # Save baseline data
        self.baseline_data = current_counts.copy()
        self._save_baseline()
        
        logger.info(f"File count baseline initialized: {current_counts}")
        return current_counts
    
    def check_new_files(self, directories: Dict[str, str]) -> Dict[str, Any]:
        """Check for new files.

        Compare the number of files in the current directory to the baseline:
        - Count the number of new additions and determine whether all engines are ready;
        - Return detailed counts and missing lists for the web layer to prompt to the user."""
        current_counts = {}
        new_files_found = {}
        all_have_new = True
        
        for engine, directory in directories.items():
            if os.path.exists(directory):
                md_files = [f for f in os.listdir(directory) if f.endswith('.md')]
                current_counts[engine] = len(md_files)
                baseline_count = self.baseline_data.get(engine, 0)
                
                if current_counts[engine] > baseline_count:
                    new_files_found[engine] = current_counts[engine] - baseline_count
                else:
                    new_files_found[engine] = 0
                    all_have_new = False
            else:
                current_counts[engine] = 0
                new_files_found[engine] = 0
                all_have_new = False
        
        return {
            'ready': all_have_new,
            'baseline_counts': self.baseline_data,
            'current_counts': current_counts,
            'new_files_found': new_files_found,
            'missing_engines': [engine for engine, count in new_files_found.items() if count == 0]
        }
    
    def get_latest_files(self, directories: Dict[str, str]) -> Dict[str, str]:
        """Get the latest files for each directory.

        Find out the most recently written Markdown via `os.path.getmtime`,
        To ensure that the generation process always uses the latest version of the three-engine report."""
        latest_files = {}
        
        for engine, directory in directories.items():
            if os.path.exists(directory):
                md_files = [f for f in os.listdir(directory) if f.endswith('.md')]
                if md_files:
                    latest_file = max(md_files, key=lambda x: os.path.getmtime(os.path.join(directory, x)))
                    latest_files[engine] = os.path.join(directory, latest_file)
        
        return latest_files


class ReportAgent:
    """Report Agent main class.

    Responsible for integrating:
    - LLM client and its upper four inference nodes;
    - Chapter storage, IR binding, renderer and other output links;
    - Status management, logging, input and output verification and persistence."""
    _CONTENT_SPARSE_MIN_ATTEMPTS = 3
    _CONTENT_SPARSE_WARNING_TEXT = "The word count of the content generated by LLM in this chapter may be too low. If necessary, you can try to rerun the program."
    _STRUCTURAL_RETRY_ATTEMPTS = 2
    
    def __init__(self, config: Optional[Settings] = None):
        """Initialize Report Agent.
        
        Args:
            config: configuration object, automatically loaded if not provided
        
        Overview of steps:
            1. Parse the configuration and access core components such as log/LLM/rendering;
            2. Construct four reasoning nodes (template, layout, length, chapter);
            3. Initialize the file base and chapter placement directory;
            4. Build a serializable state container for query by external services."""
        # Load configuration
        self.config = config or settings
        
        # Initialize File Baseline Manager
        self.file_baseline = FileCountBaseline()
        
        # Initialization log
        self._setup_logging()
        
        # Initialize LLM client
        self.llm_client = self._initialize_llm()
        self.json_rescue_clients = self._initialize_rescue_llms()
        
        # Initialize chapter-level storage/verification/rendering components
        self.chapter_storage = ChapterStorage(self.config.CHAPTER_OUTPUT_DIR)
        self.document_composer = DocumentComposer()
        self.validator = IRValidator()
        self.renderer = HTMLRenderer()
        
        # Initialize node
        self._initialize_nodes()
        
        # Initialization file number benchmark
        self._initialize_file_baseline()
        
        # state
        self.state = ReportState()
        
        # Make sure the output directory exists
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        os.makedirs(self.config.DOCUMENT_IR_OUTPUT_DIR, exist_ok=True)
        
        logger.info("Report Agent has been initialized")
        logger.info(f"Using LLM: {self.llm_client.get_model_info()}")
        
    def _setup_logging(self):
        """Setup log.

        - Make sure the log directory exists;
        - Use an independent loguru sink to write the Report Engine exclusive log file,
          Avoid confusion with other subsystems.
        - [Fix] Configure real-time log writing and disable buffering to ensure that the front end can see the logs in real time
        - [Fix] Prevent repeated addition of handler"""
        # Make sure the log directory exists
        log_dir = os.path.dirname(self.config.LOG_FILE)
        os.makedirs(log_dir, exist_ok=True)

        def _exclude_other_engines(record):
            """Filter out logs generated by other engines (Insight/Media/Query/Forum) and retain all remaining logs.

            Use path matching mainly, and fall back to the module name when the path cannot be obtained."""
            excluded_keywords = ("InsightEngine", "MediaEngine", "QueryEngine", "ForumEngine")
            try:
                file_path = record["file"].path
                if any(keyword in file_path for keyword in excluded_keywords):
                    return False
            except Exception:
                pass

            try:
                module_name = record.get("module", "")
                if isinstance(module_name, str):
                    lowered = module_name.lower()
                    if any(keyword.lower() in lowered for keyword in excluded_keywords):
                        return False
            except Exception:
                pass

            return True

        # [Fix] Check whether the handler of this file has been added to avoid duplication
        # loguru will automatically remove duplicates, but explicit checking is safer
        log_file_path = str(Path(self.config.LOG_FILE).resolve())

        # Check existing handlers
        handler_exists = False
        for handler_id, handler_config in logger._core.handlers.items():
            if hasattr(handler_config, 'sink'):
                sink = handler_config.sink
                # Check if it is a file sink and the path is the same
                if hasattr(sink, '_name') and sink._name == log_file_path:
                    handler_exists = True
                    logger.debug(f"The log handler already exists, skip adding: {log_file_path}")
                    break

        if not handler_exists:
            # [Fix] Create a dedicated logger and configure real-time writing
            # - enqueue=False: disable asynchronous queue and write immediately
            # - buffering=1: line buffering, each log is flushed to the file immediately
            # - level="DEBUG": record all levels of logs
            # - encoding="utf-8": explicitly specify UTF-8 encoding
            # - mode="a": append mode, keep historical logs
            handler_id = logger.add(
                self.config.LOG_FILE,
                level="DEBUG",
                enqueue=False,      # Disable asynchronous queue, write synchronously
                buffering=1,        # Line buffering, each line is written immediately
                serialize=False,    # Plain text format, not serialized to JSON
                encoding="utf-8",   # Explicit UTF-8 encoding
                mode="a",           # append mode
                filter=_exclude_other_engines # Filter out the logs of the four Engines and retain the remaining information
            )
            logger.debug(f"Added log handler (ID: {handler_id}): {self.config.LOG_FILE}")

        # [Fix] Verify log file is writable
        try:
            with open(self.config.LOG_FILE, 'a', encoding='utf-8') as f:
                f.write('')  # Try writing empty string to verify permissions
                f.flush()    # Refresh now
        except Exception as e:
            logger.error(f"Unable to write to log file: {self.config.LOG_FILE}, error: {e}")
            raise
        
    def _initialize_file_baseline(self):
        """Initialize file number baseline.

        Pass the three directories Insight/Media/Query into `FileCountBaseline`,
        Generate a one-time reference value, and then use increments to determine whether the three engines produce new reports."""
        directories = {
            'insight': 'insight_engine_streamlit_reports',
            'media': 'media_engine_streamlit_reports',
            'query': 'query_engine_streamlit_reports'
        }
        self.file_baseline.initialize_baseline(directories)
    
    def _initialize_llm(self) -> LLMClient:
        """Initialize the LLM client.

        Use the API Key/Model/Base URL in the configuration to build a unified
        `LLMClient` instance provides reusable reasoning entry for all nodes."""
        return LLMClient(
            api_key=self.config.REPORT_ENGINE_API_KEY,
            model_name=self.config.REPORT_ENGINE_MODEL_NAME,
            base_url=self.config.REPORT_ENGINE_BASE_URL,
        )

    def _initialize_rescue_llms(self) -> List[Tuple[str, LLMClient]]:
        """Initialize the list of LLM clients required for cross-engine chapter fixes.

        The sequence follows "Report → Forum → Insight → Media", and missing configurations will be automatically skipped."""
        clients: List[Tuple[str, LLMClient]] = []
        if self.llm_client:
            clients.append(("report_engine", self.llm_client))
        fallback_specs = [
            (
                "forum_engine",
                self.config.FORUM_HOST_API_KEY,
                self.config.FORUM_HOST_MODEL_NAME,
                self.config.FORUM_HOST_BASE_URL,
            ),
            (
                "insight_engine",
                self.config.INSIGHT_ENGINE_API_KEY,
                self.config.INSIGHT_ENGINE_MODEL_NAME,
                self.config.INSIGHT_ENGINE_BASE_URL,
            ),
            (
                "media_engine",
                self.config.MEDIA_ENGINE_API_KEY,
                self.config.MEDIA_ENGINE_MODEL_NAME,
                self.config.MEDIA_ENGINE_BASE_URL,
            ),
        ]
        for label, api_key, model_name, base_url in fallback_specs:
            if not api_key or not model_name:
                continue
            try:
                client = LLMClient(api_key=api_key, model_name=model_name, base_url=base_url)
            except Exception as exc:
                logger.warning(f"{label} LLM initialization failed, skipping the repair channel: {exc}")
                continue
            clients.append((label, client))
        return clients
    
    def _initialize_nodes(self):
        """Initialize the processing node.

        Four nodes are sequential instantiation template selection, document layout, space planning, and chapter generation.
        The chapter nodes additionally rely on the IR checker and chapter memory."""
        self.template_selection_node = TemplateSelectionNode(
            self.llm_client,
            self.config.TEMPLATE_DIR
        )
        self.document_layout_node = DocumentLayoutNode(self.llm_client)
        self.word_budget_node = WordBudgetNode(self.llm_client)
        self.chapter_generation_node = ChapterGenerationNode(
            self.llm_client,
            self.validator,
            self.chapter_storage,
            fallback_llm_clients=self.json_rescue_clients,
            error_log_dir=self.config.JSON_ERROR_LOG_DIR,
        )
    
    def generate_report(self, query: str, reports: List[Any], forum_logs: str = "",
                        custom_template: str = "", save_report: bool = True,
                        stream_handler: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> str:
        """Generate comprehensive reports (chapter JSON → IR → HTML).

        Main stages:
            1. Normalize three engine reports + forum logs, and output streaming events;
            2. Template selection → Template slicing → Document layout → Space planning;
            3. Call LLM chapter by chapter based on the length target, and automatically retry when encountering parsing errors;
            4. Bind the chapters into Document IR, and then hand it over to the HTML renderer to generate the finished product;
            5. Optionally save HTML/IR/status to disk and return path information to the outside world.

        Parameters:
            query: The final report topic or question statement to be generated.
            reports: Raw output from analytics engines such as Query/Media/Insight, allowing strings or more complex objects to be passed in.
            forum_logs: Forum/collaboration records for LLM to understand the context of multi-person discussions.
            custom_template: The Markdown template specified by the user. If it is empty, it will be automatically selected by the template node.
            save_report: Whether to automatically write HTML, IR and status to disk after generation.
            stream_handler: Optional streaming event callback, receiving stage label and payload for real-time UI display.

        Return:
            dict: A dictionary containing `html_content` and the path to the HTML/IR/status file; if `save_report=False` only returns the HTML string.

        Exception:
            Exception: Thrown when any child node or rendering phase fails, and the outer caller is responsible for taking care of it."""
        start_time = datetime.now()
        report_id = f"report-{uuid4().hex[:8]}"
        self.state.task_id = report_id
        self.state.query = query
        self.state.metadata.query = query
        self.state.mark_processing()

        normalized_reports = self._normalize_reports(reports)

        def emit(event_type: str, payload: Dict[str, Any]):
            """The event dispatcher for the Report Engine streaming channel ensures that errors are not leaked."""
            if not stream_handler:
                return
            try:
                stream_handler(event_type, payload)
            except Exception as callback_error:  # pragma: no cover - log only
                logger.warning(f"Streaming event callback failed: {callback_error}")

        logger.info(f"Start generating report {report_id}: {query}")
        logger.info(f"Input data - Number of reports: {len(reports)}, Forum log length: {len(str(forum_logs))}")
        emit('stage', {'stage': 'agent_start', 'report_id': report_id, 'query': query})

        try:
            template_result = self._select_template(query, reports, forum_logs, custom_template)
            template_result = self._ensure_mapping(
                template_result,
                "Template selection results",
                expected_keys=["template_name", "template_content"],
            )
            self.state.metadata.template_used = template_result.get('template_name', '')
            emit('stage', {
                'stage': 'template_selected',
                'template': template_result.get('template_name'),
                'reason': template_result.get('selection_reason')
            })
            emit('progress', {'progress': 10, 'message': '模板选择完成'})
            sections = self._slice_template(template_result.get('template_content', ''))
            if not sections:
                raise ValueError("The template cannot parse out chapters, please check the template content.")
            emit('stage', {'stage': 'template_sliced', 'section_count': len(sections)})

            template_text = template_result.get('template_content', '')
            template_overview = self._build_template_overview(template_text, sections)
            # Design global title, table of contents and visual theme based on template skeleton + three-engine content
            layout_design = self._run_stage_with_retry(
                "Document design",
                lambda: self.document_layout_node.run(
                    sections,
                    template_text,
                    normalized_reports,
                    forum_logs,
                    query,
                    template_overview,
                ),
                # The toc field has been replaced by tocPlan, here you select/verify according to the latest Schema
                expected_keys=["title", "hero", "tocPlan", "tocTitle"],
            )
            emit('stage', {
                'stage': 'layout_designed',
                'title': layout_design.get('title'),
                'toc': layout_design.get('tocTitle')
            })
            emit('progress', {'progress': 15, 'message': '文档标题/目录设计完成'})
            # Use the newly generated design draft to plan the length of the book and limit the number of words and key points in each chapter.
            word_plan = self._run_stage_with_retry(
                "Chapter length planning",
                lambda: self.word_budget_node.run(
                    sections,
                    layout_design,
                    normalized_reports,
                    forum_logs,
                    query,
                    template_overview,
                ),
                expected_keys=["chapters", "totalWords", "globalGuidelines"],
                postprocess=self._normalize_word_plan,
            )
            emit('stage', {
                'stage': 'word_plan_ready',
                'chapter_targets': len(word_plan.get('chapters', []))
            })
            emit('progress', {'progress': 20, 'message': '章节字数规划已生成'})
            # Record the target number of words/emphasis points of each chapter and then pass it to the chapter LLM
            chapter_targets = {
                entry.get("chapterId"): entry
                for entry in word_plan.get("chapters", [])
                if entry.get("chapterId")
            }

            generation_context = self._build_generation_context(
                query,
                normalized_reports,
                forum_logs,
                template_result,
                layout_design,
                chapter_targets,
                word_plan,
                template_overview,
            )
            # Global metadata required for IR/rendering, along with the title/theme/directory/length information given in the design draft
            manifest_meta = {
                "query": query,
                "title": layout_design.get("title") or (f"{query} - Public opinion insight report" if query else template_result.get("template_name")),
                "subtitle": layout_design.get("subtitle"),
                "tagline": layout_design.get("tagline"),
                "templateName": template_result.get("template_name"),
                "selectionReason": template_result.get("selection_reason"),
                "themeTokens": generation_context.get("theme_tokens", {}),
                "toc": {
                    "depth": 3,
                    "autoNumbering": True,
                    "title": layout_design.get("tocTitle") or "Table of contents",
                },
                "hero": layout_design.get("hero"),
                "layoutNotes": layout_design.get("layoutNotes"),
                "wordPlan": {
                    "totalWords": word_plan.get("totalWords"),
                    "globalGuidelines": word_plan.get("globalGuidelines"),
                },
                "templateOverview": template_overview,
            }
            if layout_design.get("themeTokens"):
                manifest_meta["themeTokens"] = layout_design["themeTokens"]
            if layout_design.get("tocPlan"):
                manifest_meta["toc"]["customEntries"] = layout_design["tocPlan"]
            # Initialize the chapter output directory and write it to the manifest to facilitate streaming saving.
            run_dir = self.chapter_storage.start_session(report_id, manifest_meta)
            self._persist_planning_artifacts(run_dir, layout_design, word_plan, template_overview)
            emit('stage', {'stage': 'storage_ready', 'run_dir': str(run_dir)})

            chapters = []
            chapter_max_attempts = max(
                self._CONTENT_SPARSE_MIN_ATTEMPTS, self.config.CHAPTER_JSON_MAX_ATTEMPTS
            )
            total_chapters = len(sections)  # Total number of chapters
            completed_chapters = 0  # Number of chapters completed

            for section in sections:
                logger.info(f"Generate section: {section.title}")
                emit('chapter_status', {
                    'chapterId': section.chapter_id,
                    'title': section.title,
                    'status': 'running'
                })
                # Chapter streaming callback: Transparently pass the delta returned by LLM to SSE to facilitate real-time rendering on the front end
                def chunk_callback(delta: str, meta: Dict[str, Any], section_ref: TemplateSection = section):
                    """Chapter content streaming callback.

                    Args:
                        delta: delta text of the latest LLM output.
                        meta: Chapter metadata returned by the node, used when telling the truth.
                        section_ref: points to the current section by default, ensuring that it can be located even when meta-information is missing."""
                    emit('chapter_chunk', {
                        'chapterId': meta.get('chapterId') or section_ref.chapter_id,
                        'title': meta.get('title') or section_ref.title,
                        'delta': delta
                    })

                chapter_payload: Dict[str, Any] | None = None
                attempt = 1
                best_sparse_candidate: Dict[str, Any] | None = None
                best_sparse_score = -1
                fallback_used = False
                while attempt <= chapter_max_attempts:
                    try:
                        chapter_payload = self.chapter_generation_node.run(
                            section,
                            generation_context,
                            run_dir,
                            stream_callback=chunk_callback
                        )
                        break
                    except (ChapterJsonParseError, ChapterContentError, ChapterValidationError) as structured_error:
                        if isinstance(structured_error, ChapterContentError):
                            error_kind = "content_sparse"
                            readable_label = "Abnormal content density"
                        elif isinstance(structured_error, ChapterValidationError):
                            error_kind = "validation"
                            readable_label = "Structure verification failed"
                        else:
                            error_kind = "json_parse"
                            readable_label = "JSON parsing failed"
                        if isinstance(structured_error, ChapterContentError):
                            candidate = getattr(structured_error, "chapter_payload", None)
                            candidate_score = getattr(structured_error, "body_characters", 0) or 0
                            if isinstance(candidate, dict) and candidate_score >= 0:
                                if candidate_score > best_sparse_score:
                                    best_sparse_candidate = deepcopy(candidate)
                                    best_sparse_score = candidate_score
                        will_fallback = (
                            isinstance(structured_error, ChapterContentError)
                            and attempt >= chapter_max_attempts
                            and attempt >= self._CONTENT_SPARSE_MIN_ATTEMPTS
                            and best_sparse_candidate is not None
                        )
                        logger.warning(
                            "Chapter {title} {label} (attempt {attempt}/{total}): {error}",
                            title=section.title,
                            label=readable_label,
                            attempt=attempt,
                            total=chapter_max_attempts,
                            error=structured_error,
                        )
                        status_value = 'retrying' if attempt < chapter_max_attempts or will_fallback else 'error'
                        status_payload = {
                            'chapterId': section.chapter_id,
                            'title': section.title,
                            'status': status_value,
                            'attempt': attempt,
                            'error': str(structured_error),
                            'reason': error_kind,
                        }
                        if isinstance(structured_error, ChapterValidationError):
                            validation_errors = getattr(structured_error, "errors", None)
                            if validation_errors:
                                status_payload['errors'] = validation_errors
                        if will_fallback:
                            status_payload['warning'] = 'content_sparse_fallback_pending'
                        emit('chapter_status', status_payload)
                        if will_fallback:
                            logger.warning(
                                "Chapter {title} reaches the maximum number of attempts, and the version with the largest number of words (about {score} words) is retained as the bottom output.",
                                title=section.title,
                                score=best_sparse_score,
                            )
                            chapter_payload = self._finalize_sparse_chapter(best_sparse_candidate)
                            fallback_used = True
                            break
                        if attempt >= chapter_max_attempts:
                            raise
                        attempt += 1
                        continue
                    except Exception as chapter_error:
                        if not self._should_retry_inappropriate_content_error(chapter_error):
                            raise
                        logger.warning(
                            "Chapter {title} triggered content security restrictions (attempt {attempt}/{total}), ready to regenerate: {error}",
                            title=section.title,
                            attempt=attempt,
                            total=chapter_max_attempts,
                            error=chapter_error,
                        )
                        emit('chapter_status', {
                            'chapterId': section.chapter_id,
                            'title': section.title,
                            'status': 'retrying' if attempt < chapter_max_attempts else 'error',
                            'attempt': attempt,
                            'error': str(chapter_error),
                            'reason': 'content_filter'
                        })
                        if attempt >= chapter_max_attempts:
                            raise
                        attempt += 1
                        continue
                if chapter_payload is None:
                    raise ChapterJsonParseError(
                        f"{section.title} Chapter JSON could not be parsed after {chapter_max_attempts} attempts"
                    )
                chapters.append(chapter_payload)
                completed_chapters += 1  # Update number of completed chapters
                # Calculate current progress: 20% + 80% * (number of chapters completed / total number of chapters), rounded
                chapter_progress = 20 + round(80 * completed_chapters / total_chapters)
                emit('progress', {
                    'progress': chapter_progress,
                    'message': f'章节 {completed_chapters}/{total_chapters} 已完成'
                })
                completion_status = {
                    'chapterId': section.chapter_id,
                    'title': section.title,
                    'status': 'completed',
                    'attempt': attempt,
                }
                if fallback_used:
                    completion_status['warning'] = 'content_sparse_fallback'
                    completion_status['warningMessage'] = self._CONTENT_SPARSE_WARNING_TEXT
                emit('chapter_status', completion_status)

            document_ir = self.document_composer.build_document(
                report_id,
                manifest_meta,
                chapters
            )
            emit('stage', {'stage': 'chapters_compiled', 'chapter_count': len(chapters)})
            html_report = self.renderer.render(document_ir)
            emit('stage', {'stage': 'html_rendered', 'html_length': len(html_report)})

            self.state.html_content = html_report
            self.state.mark_completed()

            saved_files = {}
            if save_report:
                saved_files = self._save_report(html_report, document_ir, report_id)
                emit('stage', {'stage': 'report_saved', 'files': saved_files})

            generation_time = (datetime.now() - start_time).total_seconds()
            self.state.metadata.generation_time = generation_time
            logger.info(f"Report generation completed, taking: {generation_time:.2f} seconds")
            emit('metrics', {'generation_seconds': generation_time})
            return {
                'html_content': html_report,
                'report_id': report_id,
                **saved_files
            }

        except Exception as e:
            self.state.mark_failed(str(e))
            logger.exception(f"An error occurred during report generation: {str(e)}")
            emit('error', {'stage': 'agent_failed', 'message': str(e)})
            raise
    
    def _select_template(self, query: str, reports: List[Any], forum_logs: str, custom_template: str):
        """Select a report template.

        Priority is given to using user-specified templates; otherwise, queries, three-engine reports and forum logs will be
        Passed to TemplateSelectionNode as context, LLM returns the most suitable
        Template name, content and reason, and automatically recorded in the status.

        Parameters:
            query: report topic, used to prompt words to focus on industries/events.
            reports: The original text of multi-source reports helps LLM determine the structural complexity.
            forum_logs: Text corresponding to forum or collaborative discussions, used to supplement background.
            custom_template: Custom Markdown template passed in from CLI/front-end, used directly if it is not empty.

        Return:
            dict: A structured result containing `template_name`, `template_content` and `selection_reason` for consumption by subsequent nodes."""
        logger.info("Select report template...")
        
        # If the user provides a custom template, use it directly
        if custom_template:
            logger.info("Use user-defined templates")
            return {
                'template_name': 'custom',
                'template_content': custom_template,
                'selection_reason': '用户指定的自定义模板'
            }
        
        template_input = {
            'query': query,
            'reports': reports,
            'forum_logs': forum_logs
        }
        
        try:
            template_result = self.template_selection_node.run(template_input)
            
            # update status
            self.state.metadata.template_used = template_result['template_name']
            
            logger.info(f"Select template: {template_result['template_name']}")
            logger.info(f"Reason for selection: {template_result['selection_reason']}")
            
            return template_result
        except Exception as e:
            logger.error(f"Template selection failed, using default template: {str(e)}")
            # Use the backup template directly
            fallback_template = {
                'template_name': '社会公共热点事件分析报告模板',
                'template_content': self._get_fallback_template_content(),
                'selection_reason': '模板选择失败，使用默认社会热点事件分析模板'
            }
            self.state.metadata.template_used = fallback_template['template_name']
            return fallback_template
    
    def _slice_template(self, template_markdown: str) -> List[TemplateSection]:
        """Cut the template into a chapter list, and provide a fallback if it is empty.

        Delegate `parse_template_sections` to parse Markdown titles/numbers into
        `TemplateSection` list to ensure that subsequent chapters are generated with stable chapter IDs.
        When the template format is abnormal, it will fall back to the built-in simple skeleton to avoid crashes.

        Parameters:
            template_markdown: Complete template Markdown text.

        Return:
            list[TemplateSection]: parsed chapter sequence; if parsing fails, a single chapter summary structure will be returned."""
        sections = parse_template_sections(template_markdown)
        if sections:
            return sections
        logger.warning("The template does not parse out chapters and uses the default chapter skeleton.")
        fallback = TemplateSection(
            title="1.0 Comprehensive analysis",
            slug="section-1-0",
            order=10,
            depth=1,
            raw_title="1.0 Comprehensive analysis",
            number="1.0",
            chapter_id="S1",
            outline=["1.1 Summary", "1.2 Data Highlights", "1.3 Risk warning"],
        )
        return [fallback]

    def _build_generation_context(
        self,
        query: str,
        reports: Dict[str, str],
        forum_logs: str,
        template_result: Dict[str, Any],
        layout_design: Dict[str, Any],
        chapter_directives: Dict[str, Any],
        word_plan: Dict[str, Any],
        template_overview: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Construct the shared context required for chapter generation.

        Change the template name, layout design, theme color, space planning, forum log, etc.
        Integrated into `generation_context` at one time, when LLM is called in each subsequent chapter
        Direct reuse ensures all chapters share a consistent tone and visual constraints.

        Parameters:
            query: user query word.
            reports: Normalized query/media/insight report mapping.
            forum_logs: Three-engine discussion records.
            template_result: Template meta-information returned by the template node.
            layout_design: The title/table of contents/theme design produced by the document layout node.
            chapter_directives: The chapter directive mapping returned by the word count planning node.
            word_plan: The original result of space planning, including global word count constraints.
            template_overview: Chapter skeleton summary extracted from template slices.

        Return:
            dict: The complete context required for LLM chapter generation, including keys such as theme color, layout, and constraints."""
        # Give priority to using the theme color customized by the design draft, otherwise return to the default theme
        theme_tokens = (
            layout_design.get("themeTokens")
            if layout_design else None
        ) or self._default_theme_tokens()

        return {
            "query": query,
            "template_name": template_result.get("template_name"),
            "reports": reports,
            "forum_logs": self._stringify(forum_logs),
            "theme_tokens": theme_tokens,
            "style_directives": {
                "tone": "analytical",
                "audience": "executive",
                "language": "zh-CN",
            },
            "data_bundles": [],
            "max_tokens": min(self.config.MAX_CONTENT_LENGTH, 6000),
            "layout": layout_design or {},
            "template_overview": template_overview or {},
            "chapter_directives": chapter_directives or {},
            "word_plan": word_plan or {},
        }

    def _normalize_reports(self, reports: List[Any]) -> Dict[str, str]:
        """Convert reports from different sources into strings.

        The agreed order is Query/Media/Insight, and the objects provided by the engine may be
        Dictionary or custom type, so use `_stringify` for fault tolerance.

        Parameters:
            reports: A list of reports of any type, missing or out of order allowed.

        Return:
            dict: Contains a mapping of three string fields `query_engine`/`media_engine`/`insight_engine`."""
        keys = ["query_engine", "media_engine", "insight_engine"]
        normalized: Dict[str, str] = {}
        for idx, key in enumerate(keys):
            value = reports[idx] if idx < len(reports) else ""
            normalized[key] = self._stringify(value)
        return normalized

    def _should_retry_inappropriate_content_error(self, error: Exception) -> bool:
        """Determine whether the LLM exception is caused by safe/inappropriate content.

        Allow chapter generation when errors returned by the vendor are detected to contain specific keywords
        Try again to bypass occasional content review triggers.

        Parameters:
            error: exception object thrown by LLM client.

        Return:
            bool: Returns True if the content review keyword is matched, otherwise False."""
        message = str(error) if error else ""
        if not message:
            return False
        normalized = message.lower()
        keywords = [
            "inappropriate content",
            "content violation",
            "content moderation",
            "model-studio/error-code",
        ]
        return any(keyword in normalized for keyword in keywords)

    def _run_stage_with_retry(
        self,
        stage_name: str,
        fn: Callable[[], Any],
        expected_keys: Optional[List[str]] = None,
        postprocess: Optional[Callable[[Dict[str, Any], str], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Run a single LLM stage with a limited number of retries in case of structural anomalies.

        This method only performs local repair/retry for structural errors to avoid restarting the entire Agent."""
        last_error: Optional[Exception] = None
        for attempt in range(1, self._STRUCTURAL_RETRY_ATTEMPTS + 1):
            try:
                raw_result = fn()
                result = self._ensure_mapping(raw_result, stage_name, expected_keys)
                if postprocess:
                    result = postprocess(result, stage_name)
                return result
            except StageOutputFormatError as exc:
                last_error = exc
                logger.warning(
                    "{stage} output structure exception ({attempt}/{total} time), will try to repair or retry: {error}",
                    stage=stage_name,
                    attempt=attempt,
                    total=self._STRUCTURAL_RETRY_ATTEMPTS,
                    error=exc,
                )
                if attempt >= self._STRUCTURAL_RETRY_ATTEMPTS:
                    break
        raise last_error  # type: ignore[misc]

    def _ensure_mapping(
        self,
        value: Any,
        context: str,
        expected_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Make sure the stage output is a dict; if returning a list try to extract the best matching element."""
        if isinstance(value, dict):
            return value

        if isinstance(value, list):
            candidates = [item for item in value if isinstance(item, dict)]
            if candidates:
                best = candidates[0]
                if expected_keys:
                    candidates.sort(
                        key=lambda item: sum(1 for key in expected_keys if key in item),
                        reverse=True,
                    )
                    best = candidates[0]
                logger.warning(
                    "{context} returns a list, the element containing the most expected keys has been automatically extracted and execution continues",
                    context=context,
                )
                return best
            raise StageOutputFormatError(f"{context} returns a list but lacks available object elements")

        if value is None:
            raise StageOutputFormatError(f"{context} returns empty results")

        raise StageOutputFormatError(
            f"{context} return type {type(value).__name__}, dictionary expected"
        )

    def _normalize_word_plan(self, word_plan: Dict[str, Any], stage_name: str) -> Dict[str, Any]:
        """Clean page planning results to ensure chapters/globalGuidelines/totalWords type safety."""
        raw_chapters = word_plan.get("chapters", [])
        if isinstance(raw_chapters, dict):
            chapters_iterable = raw_chapters.values()
        elif isinstance(raw_chapters, list):
            chapters_iterable = raw_chapters
        else:
            chapters_iterable = []

        normalized: List[Dict[str, Any]] = []
        for idx, entry in enumerate(chapters_iterable):
            if isinstance(entry, dict):
                normalized.append(entry)
                continue
            if isinstance(entry, list):
                dict_candidate = next((item for item in entry if isinstance(item, dict)), None)
                if dict_candidate:
                    logger.warning(
                        "{stage} The {idx}th chapter entry is a list, and the first object has been extracted for subsequent processes.",
                        stage=stage_name,
                        idx=idx + 1,
                    )
                    normalized.append(dict_candidate)
                    continue
            logger.warning(
                "{stage} Skip unresolved chapter entry #{idx} (type: {type_name})"})",
                stage=stage_name,
                idx=idx + 1,
                type_name=type(entry).__name__,
            )

        if not normalized:
            raise StageOutputFormatError(f"{stage_name} lacks a valid chapter plan and cannot continue.")

        word_plan["chapters"] = normalized

        guidelines = word_plan.get("globalGuidelines")
        if not isinstance(guidelines, list):
            if guidelines is None or guidelines == "":
                word_plan["globalGuidelines"] = []
            else:
                logger.warning(
                    "{stage} globalGuidelines type exception, has been converted to list encapsulation",
                    stage=stage_name,
                )
                word_plan["globalGuidelines"] = [guidelines]

        if not isinstance(word_plan.get("totalWords"), (int, float)):
            logger.warning(
                "{stage} totalWords type exception, use the default value 10000",
                stage=stage_name,
            )
            word_plan["totalWords"] = 10000

        return word_plan

    def _finalize_sparse_chapter(self, chapter: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Construct a sparse and informative chapter: copy the original payload and insert a warm reminder paragraph."""
        safe_chapter = deepcopy(chapter or {})
        if not isinstance(safe_chapter, dict):
            safe_chapter = {}
        self._ensure_sparse_warning_block(safe_chapter)
        return safe_chapter

    def _ensure_sparse_warning_block(self, chapter: Dict[str, Any]) -> None:
        """Insert a reminder paragraph after the chapter title to remind readers that the chapter has a short word count."""
        warning_block = {
            "type": "paragraph",
            "inlines": [
                {
                    "text": self._CONTENT_SPARSE_WARNING_TEXT,
                    "marks": [{"type": "italic"}],
                }
            ],
            "meta": {"role": "content-sparse-warning"},
        }
        blocks = chapter.get("blocks")
        if isinstance(blocks, list) and blocks:
            inserted = False
            for idx, block in enumerate(blocks):
                if isinstance(block, dict) and block.get("type") == "heading":
                    blocks.insert(idx + 1, warning_block)
                    inserted = True
                    break
            if not inserted:
                blocks.insert(0, warning_block)
        else:
            chapter["blocks"] = [warning_block]
        meta = chapter.get("meta")
        if isinstance(meta, dict):
            meta["contentSparseWarning"] = True
        else:
            chapter["meta"] = {"contentSparseWarning": True}

    def _stringify(self, value: Any) -> str:
        """Safely convert objects to strings.

        - dict/list is uniformly serialized into formatted JSON to facilitate prompt word consumption;
        - For other types, use `str()`. If None, an empty string is returned to avoid None propagation.

        Parameters:
            value: any Python object.

        Return:
            str: String representation of adapted prompt words/logs."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False, indent=2)
            except Exception:
                return str(value)
        return str(value)

    def _default_theme_tokens(self) -> Dict[str, Any]:
        """Construct default theme variables for renderer/LLM sharing.

        Use this color palette when the layout node does not return a dedicated color palette to keep the report style unified.

        Return:
            dict: A theme dictionary containing rendering parameters such as color, font, spacing, and boolean switches."""
        return {
            "colors": {
                "bg": "#f8f9fa",
                "text": "#212529",
                "primary": "#007bff",
                "secondary": "#6c757d",
                "card": "#ffffff",
                "border": "#dee2e6",
                "accent1": "#17a2b8",
                "accent2": "#28a745",
                "accent3": "#ffc107",
                "accent4": "#dc3545",
            },
            "fonts": {
                "body": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif",
                "heading": "'Source Han Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif",
            },
            "spacing": {"container": "1200px", "gutter": "24px"},
            "vars": {
                "header_sticky": True,
                "toc_depth": 3,
                "enable_dark_mode": True,
            },
        }

    def _build_template_overview(
        self,
        template_markdown: str,
        sections: List[TemplateSection],
    ) -> Dict[str, Any]:
        """Extract the template title and chapter skeleton for unified reference in design/length planning.

        At the same time, auxiliary fields such as chapter ID/slug/order are recorded to ensure multi-node alignment.

        Parameters:
            template_markdown: template original text, used to parse global titles.
            sections: `TemplateSection` list, used as a section skeleton.

        Return:
            dict: An overview structure containing template titles and chapter metadata."""
        fallback_title = sections[0].title if sections else ""
        overview = {
            "title": self._extract_template_title(template_markdown, fallback_title),
            "chapters": [],
        }
        for section in sections:
            overview["chapters"].append(
                {
                    "chapterId": section.chapter_id,
                    "title": section.title,
                    "rawTitle": section.raw_title,
                    "number": section.number,
                    "slug": section.slug,
                    "order": section.order,
                    "depth": section.depth,
                    "outline": section.outline,
                }
            )
        return overview

    @staticmethod
    def _extract_template_title(template_markdown: str, fallback: str = "") -> str:
        """Try extracting the first title from Markdown.

        The first `#` syntax title will be returned first; if the first line of the template is the text, it will fall back to
        The first line of non-empty text or a caller-supplied fallback.

        Parameters:
            template_markdown: template original text.
            fallback: Fallback title, used when the document lacks an explicit title.

        Return:
            str: The parsed title text."题时使用。

        返回:
            str: 解析到的标题文本。
        """
        for line in template_markdown.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
            if stripped:
                fallback = fallback or stripped
        return fallback or "Intelligent public opinion analysis report"
    
    def _get_fallback_template_content(self) -> str:
        """Get the alternate template content.

        This Markdown template is used when the template directory is not available or LLM selection fails,
        Ensure that subsequent processes can still provide structured chapters."""
        return """# Social and public hot event analysis report

## Executive summary
This report provides a comprehensive analysis of current social hot events, integrating views and data from multiple information sources.

## Event Overview
### Basic information
- Event nature: {event_nature}
- Occurrence time: {event_time}
- Scope involved: {event_scope}

## Public opinion situation analysis
### Overall trend
{sentiment_analysis}

### Distribution of main points
{opinion_distribution}

## Media report analysis
### Mainstream media attitude
{media_analysis}

### Highlights of the report
{report_focus}

## Social Impact Assessment
### Direct impact
{direct_impact}

### Potential Impact
{potential_impact}

## Response suggestions
### Immediate measures
{immediate_actions}

### Long-term strategy
{long_term_strategy}

## Conclusion and Outlook
{conclusion}

---
*Report type: Analysis of social and public hot events*
*Generation time: {generation_time}*"t
# ## Direct impact
{direct_impact}

# ## Potential Impact
{potential_impact}

# # Response suggestions
# ## Immediate measures
{immediate_actions}

# ## Long term strategy
{long_term_strategy}

# # Conclusion and Outlook
{conclusion}

---
*报告类型：社会公共热点事件分析*
*生成时间：{generation_time}*
"""
    
    def _save_report(self, html_content: str, document_ir: Dict[str, Any], report_id: str) -> Dict[str, Any]:
        """Save HTML and IR to file and return path information.

        Generate human-readable file names based on queries and timestamps, while also converting runtime
        `ReportState` is written into JSON to facilitate downstream troubleshooting or breakpoint continuation.

        Parameters:
            html_content: Rendered HTML text.
            document_ir: Document IR structured data.
            report_id: Current task ID, used to create an independent file name.

        Return:
            dict: records the absolute and relative path information of HTML/IR/State files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_safe = "".join(
            c for c in self.state.metadata.query if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        query_safe = query_safe.replace(" ", "_")[:30] or "report"

        html_filename = f"final_report_{query_safe}_{timestamp}.html"
        html_path = Path(self.config.OUTPUT_DIR) / html_filename
        html_path.write_text(html_content, encoding="utf-8")
        html_abs = str(html_path.resolve())
        html_rel = os.path.relpath(html_abs, os.getcwd())

        ir_path = self._save_document_ir(document_ir, query_safe, timestamp)
        ir_abs = str(ir_path.resolve())
        ir_rel = os.path.relpath(ir_abs, os.getcwd())

        state_filename = f"report_state_{query_safe}_{timestamp}.json"
        state_path = Path(self.config.OUTPUT_DIR) / state_filename
        self.state.save_to_file(str(state_path))
        state_abs = str(state_path.resolve())
        state_rel = os.path.relpath(state_abs, os.getcwd())

        logger.info(f"HTML report saved: {html_path}")
        logger.info(f"Document IR saved: {ir_path}")
        logger.info(f"State saved to: {state_path}")
        
        return {
            'report_filename': html_filename,
            'report_filepath': html_abs,
            'report_relative_path': html_rel,
            'ir_filename': ir_path.name,
            'ir_filepath': ir_abs,
            'ir_relative_path': ir_rel,
            'state_filename': state_filename,
            'state_filepath': state_abs,
            'state_relative_path': state_rel,
        }

    def _save_document_ir(self, document_ir: Dict[str, Any], query_safe: str, timestamp: str) -> Path:
        """Write the entire IR to a separate directory.

        `Document IR` is saved decoupled from HTML to facilitate debugging rendering differences and
        Render again or export to other formats without re-running LLM.

        Parameters:
            document_ir: IR structure of the entire report.
            query_safe: Cleaned query phrase used for file naming.
            timestamp: running timestamp to ensure unique file names.

        Return:
            Path: Points to the saved IR file path."""
        filename = f"report_ir_{query_safe}_{timestamp}.json"
        ir_path = Path(self.config.DOCUMENT_IR_OUTPUT_DIR) / filename
        ir_path.write_text(
            json.dumps(document_ir, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return ir_path
    
    def _persist_planning_artifacts(
        self,
        run_dir: Path,
        layout_design: Dict[str, Any],
        word_plan: Dict[str, Any],
        template_overview: Dict[str, Any],
    ):
        """Save the document design draft, space plan and template overview as JSON.

        These middleware files (document_layout/word_plan/template_overview)
        Facilitates quick positioning during debugging or review: how the title/directory/topic is determined,
        What are the requirements for word count allocation to facilitate subsequent manual correction?

        Parameters:
            run_dir: Chapter output root directory.
            layout_design: The raw output of the document layout node.
            word_plan: Word planning node output.
            template_overview: Template overview JSON."""
        artifacts = {
            "document_layout": layout_design,
            "word_plan": word_plan,
            "template_overview": template_overview,
        }
        for name, payload in artifacts.items():
            if not payload:
                continue
            path = run_dir / f"{name}.json"
            try:
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as exc:
                logger.warning(f"Failed to write {name}: {exc}")
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """Get the progress summary and directly return the serializable status dictionary for API layer query."""
        return self.state.to_dict()
    
    def load_state(self, filepath: str):
        """Load the state from the file and overwrite the current state to facilitate breakpoint recovery."""
        self.state = ReportState.load_from_file(filepath)
        logger.info(f"Status loaded from {filepath}")
    
    def save_state(self, filepath: str):
        """Save the status to a file, usually used for analysis and backup after the task is completed."""
        self.state.save_to_file(filepath)
        logger.info(f"Status saved to {filepath}")
    
    def check_input_files(self, insight_dir: str, media_dir: str, query_dir: str, forum_log_path: str) -> Dict[str, Any]:
        """Check if the input files are ready (based on increasing number of files).
        
        Args:
            insight_dir: InsightEngine report directory
            media_dir: MediaEngine report directory
            query_dir: QueryEngine report directory
            forum_log_path: Forum log file path
            
        Returns:
            Check result dictionary, including file count, missing list, latest file path, etc."""
        # Check the changes in the number of files in each report directory
        directories = {
            'insight': insight_dir,
            'media': media_dir,
            'query': query_dir
        }
        
        # Check for new files using the File Baseline Manager
        check_result = self.file_baseline.check_new_files(directories)
        
        # Check forum logs
        forum_ready = os.path.exists(forum_log_path)
        
        # Build return results
        result = {
            'ready': check_result['ready'] and forum_ready,
            'baseline_counts': check_result['baseline_counts'],
            'current_counts': check_result['current_counts'],
            'new_files_found': check_result['new_files_found'],
            'missing_files': [],
            'files_found': [],
            'latest_files': {}
        }
        
        # Build details
        for engine, new_count in check_result['new_files_found'].items():
            current_count = check_result['current_counts'][engine]
            baseline_count = check_result['baseline_counts'].get(engine, 0)
            
            if new_count > 0:
                result['files_found'].append(f"{engine}: {current_count} files ({new_count} added)")
            else:
                result['missing_files'].append(f"{engine}: {current_count} files (baseline_count}, no new ones)")
        
        # Check forum logs
        if forum_ready:
            result['files_found'].append(f"forum: {os.path.basename(forum_log_path)}")
        else:
            result['missing_files'].append("forum: log file does not exist")
        
        # Get the latest file path (for actual report generation)
        if result['ready']:
            result['latest_files'] = self.file_baseline.get_latest_files(directories)
            if forum_ready:
                result['latest_files']['forum'] = forum_log_path
        
        return result
    
    def load_input_files(self, file_paths: Dict[str, str]) -> Dict[str, Any]:
        """Load input file contents
        
        Args:
            file_paths: dictionary of file paths
            
        Returns:
            Loaded content dictionary, containing `reports` list and `forum_logs` string"""
        content = {
            'reports': [],
            'forum_logs': ''
        }
        
        # Load report file
        engines = ['query', 'media', 'insight']
        for engine in engines:
            if engine in file_paths:
                try:
                    with open(file_paths[engine], 'r', encoding='utf-8') as f:
                        report_content = f.read()
                    content['reports'].append(report_content)
                    logger.info(f"{engine} report loaded: {len(report_content)} characters")
                except Exception as e:
                    logger.exception(f"Failed to load {engine} report: {str(e)}")
                    content['reports'].append("")
        
        # Load forum log
        if 'forum' in file_paths:
            try:
                with open(file_paths['forum'], 'r', encoding='utf-8') as f:
                    content['forum_logs'] = f.read()
                logger.info(f"Forum logs loaded: {len(content['forum_logs'])} characters")
            except Exception as e:
                logger.exception(f"Failed to load forum log: {str(e)}")
        
        return content


def create_agent(config_file: Optional[str] = None) -> ReportAgent:
    """Convenience function for creating Report Agent instances.
    
    Args:
        config_file: configuration file path
        
    Returns:
        ReportAgent instance

    Currently, `Settings` is driven by environment variables, and `config_file` parameters are reserved for future expansion."""
    
    config = Settings() # Initialized with empty configuration and initialized from environment variables
    return ReportAgent(config)
