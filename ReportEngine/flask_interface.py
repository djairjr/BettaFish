"""Report Engine Flask interface.

This module provides a unified HTTP/SSE entry for the front-end/CLI and is responsible for:
1. Initialize ReportAgent and connect background threads in series;
2. Manage task queuing, progress query, streaming push and log download;
3. Provide peripheral capabilities such as template list and input file checking."""

import os
import json
import threading
import time
from collections import deque, defaultdict
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from flask import Blueprint, request, jsonify, Response, send_file, stream_with_context
from typing import Dict, Any, List, Optional
from loguru import logger
from .agent import ReportAgent, create_agent
from .nodes import ChapterJsonParseError
from .utils.config import settings


# Create Blueprint
report_bp = Blueprint('report_engine', __name__)

# global variables
report_agent = None
current_task = None
task_lock = threading.Lock()

# ====== Streaming push and task history management ======
# Cache recent events through bounded deque to facilitate quick reissue after SSE is disconnected
MAX_TASK_HISTORY = 5
STREAM_HEARTBEAT_INTERVAL = 15  # heartbeat interval seconds
STREAM_IDLE_TIMEOUT = 120  # Maximum keep-alive time after final state to avoid orphan SSE blocking
STREAM_TERMINAL_STATUSES = {"completed", "error", "cancelled"}
stream_lock = threading.Lock()
stream_subscribers = defaultdict(list)
tasks_registry: Dict[str, 'ReportTask'] = {}
LOG_STREAM_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
log_stream_handler_id: Optional[int] = None

EXCLUDED_ENGINE_PATH_KEYWORDS = ("ForumEngine", "InsightEngine", "MediaEngine", "QueryEngine")

def _is_excluded_engine_log(record: Dict[str, Any]) -> bool:
    """Determine whether the logs come from other engines (Insight/Media/Query/Forum) to filter mixed logs.

    Return:
        bool: True indicates that filtering should be performed (i.e. no writing/no forwarding)."""
    try:
        file_path = record["file"].path
        if any(keyword in file_path for keyword in EXCLUDED_ENGINE_PATH_KEYWORDS):
            return True
    except Exception:
        pass

    # Bottom line: Try filtering by module name to prevent accidental mixing when file information is missing.
    try:
        module_name = record.get("module", "")
        if isinstance(module_name, str):
            lowered = module_name.lower()
            return any(keyword.lower() in lowered for keyword in EXCLUDED_ENGINE_PATH_KEYWORDS)
    except Exception:
        pass

    return False


def _stream_log_to_task(message):
    """Synchronize loguru logs to the SSE events of the current task to ensure real-time visibility on the front end.

    Only push when there are running tasks to avoid irrelevant logs from being flushed."""
    try:
        record = message.record
        level_name = record["level"].name
        if level_name not in LOG_STREAM_LEVELS:
            return
        if _is_excluded_engine_log(record):
            return

        with task_lock:
            task = current_task

        if not task or task.status not in ("running", "pending"):
            return

        timestamp = record["time"].strftime("%H:%M:%S.%f")[:-3]
        formatted_line = f"[{timestamp}] [{level_name}] {record['message']}"
        task.publish_event(
            "log",
            {
                "line": formatted_line,
                "level": level_name.lower(),
                "timestamp": timestamp,
                "message": record["message"],
                "module": record.get("module", ""),
                "function": record.get("function", ""),
            },
        )
    except Exception:
        # Avoid logging recursion in logging hooks
        pass


def _setup_log_stream_forwarder():
    """Mount a one-time loguru hook for the current process for SSE real-time forwarding."""
    global log_stream_handler_id
    if log_stream_handler_id is not None:
        return
    log_stream_handler_id = logger.add(
        _stream_log_to_task,
        level="DEBUG",
        enqueue=False,
        catch=True,
    )


def _register_stream(task_id: str) -> Queue:
    """Register an event queue for the specified task for consumption by the SSE listener.

    The returned Queue will be stored in `stream_subscribers`, and the SSE generator will continuously read it.

    Parameters:
        task_id: The task ID that needs to be monitored.

    Return:
        Queue: Thread-safe event queue."""
    queue = Queue()
    with stream_lock:
        stream_subscribers[task_id].append(queue)
    return queue


def _unregister_stream(task_id: str, queue: Queue):
    """Safely remove event queues to avoid memory leaks.

    It needs to be called in finally to ensure that resources can be released under abnormal circumstances.

    Parameters:
        task_id: task ID.
        queue: previously registered event queue."""
    with stream_lock:
        listeners = stream_subscribers.get(task_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners and task_id in stream_subscribers:
            stream_subscribers.pop(task_id, None)


def _broadcast_event(task_id: str, event: Dict[str, Any]):
    """Push the event to all listeners and catch exceptions in case of failure.

    Use a shallow copy listening list to prevent traversal exceptions caused by concurrent removal.

    Parameters:
        task_id: ID of the task to be pushed.
        event: structured event payload."""
    with stream_lock:
        listeners = list(stream_subscribers.get(task_id, []))
    for queue in listeners:
        try:
            queue.put(event, timeout=0.1)
        except Exception:
            logger.exception("Failed to push streaming events, skipping the current listening queue")


def _prune_task_history_locked():
    """Called during task_lock holding period to clean up excessive historical tasks.

    Only keep the most recent `MAX_TASK_HISTORY` tasks to avoid taking up too much memory when running for a long time.

    Description:
        This function assumes that the caller has acquired `task_lock`, otherwise there is a risk of race condition."""
    if len(tasks_registry) <= MAX_TASK_HISTORY:
        return
    # Sort by creation time, removing oldest tasks
    sorted_tasks = sorted(tasks_registry.values(), key=lambda t: t.created_at)
    for task in sorted_tasks[:-MAX_TASK_HISTORY]:
        tasks_registry.pop(task.task_id, None)


def _get_task(task_id: str) -> Optional['ReportTask']:
    """A unified task search method that returns the current task first.

    Avoid duplicating lock logic and facilitate sharing among multiple APIs.

    Parameters:
        task_id: task ID.

    Return:
        ReportTask | None: Returns the task instance if hit, None otherwise."""
    with task_lock:
        if current_task and current_task.task_id == task_id:
            return current_task
        return tasks_registry.get(task_id)


def _format_sse(event: Dict[str, Any]) -> str:
    """Format messages according to SSE protocol.

    Output three pieces of text in the form of `id:/event:/data:` for direct consumption by the browser.

    Parameters:
        event: event payload, including at least id/type.

    Return:
        str: String required by the SSE protocol."""
    payload = json.dumps(event, ensure_ascii=False)
    event_id = event.get('id', 0)
    event_type = event.get('type', 'message')
    return f"id: {event_id}\nevent: {event_type}\ndata: {payload}\n\n"


def _safe_filename_segment(value: str, fallback: str = "report") -> str:
    """Generates safe fragments that can be used in file names, preserving alphanumeric and common delimiters.

    Parameters:
        value: original string.
        fallback: Fallback text, used when value is empty or empty after cleaning."""
    sanitized = "".join(c for c in str(value) if c.isalnum() or c in (" ", "-", "_")).strip()
    sanitized = sanitized.replace(" ", "_")
    return sanitized or fallback


def initialize_report_engine():
    """Initialize Report Engine.

    Singletonize ReportAgent to facilitate receiving tasks directly after the API is started.

    Return:
        bool: Return True if initialization is successful, False if exception occurs."""
    global report_agent
    try:
        report_agent = create_agent()
        logger.info("Report Engine initialized successfully")
        _setup_log_stream_forwarder()

        # Detecting PDF generation dependencies (Pango)
        try:
            from .utils.dependency_check import log_dependency_status
            log_dependency_status()
        except Exception as dep_err:
            logger.warning(f"Dependency check failed: {dep_err}")

        return True
    except Exception as e:
        logger.exception(f"Report Engine initialization failed: {str(e)}")
        return False


class ReportTask:
    """Report generation task.

    This object concatenates running status, progress, event history and final file path.
    It is used both for background thread updates and HTTP interface reading."""

    def __init__(self, query: str, task_id: str, custom_template: str = ""):
        """Initialize the task object and record query terms, custom templates and runtime metadata.

        Args:
            query: the final report topic that needs to be generated
            task_id: Task unique ID, usually constructed from timestamp
            custom_template: Optional custom Markdown template"""
        self.task_id = task_id
        self.query = query
        self.custom_template = custom_template
        self.status = "pending"  # Four states (pending/running/completed/error)
        self.progress = 0
        self.result = None
        self.error_message = ""
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.html_content = ""
        self.report_file_path = ""
        self.report_file_relative_path = ""
        self.report_file_name = ""
        self.state_file_path = ""
        self.state_file_relative_path = ""
        self.ir_file_path = ""
        self.ir_file_relative_path = ""
        self.markdown_file_path = ""
        self.markdown_file_relative_path = ""
        self.markdown_file_name = ""
        # ====== Streaming event caching and concurrency protection ======
        # Use deque to save recent events, and combine with locks to ensure safe access under multi-threads
        self.event_history: deque = deque(maxlen=1000)
        self._event_lock = threading.Lock()
        self.last_event_id = 0

    def update_status(self, status: str, progress: int = None, error_message: str = ""):
        """Update task status and broadcast events.

        Will automatically refresh `updated_at`, error information, and trigger SSE of `status` type.

        Parameters:
            status: task stage (pending/running/completed/error/cancelled).
            progress: optional progress percentage.
            error_message: A human-readable description of the error."""
        self.status = status
        if progress is not None:
            self.progress = progress
        if error_message:
            self.error_message = error_message
        self.updated_at = datetime.now()
        # Push status change events to facilitate real-time refresh of the front end
        self.publish_event(
            'status',
            {
                'status': self.status,
                'progress': self.progress,
                'error_message': self.error_message,
                'hint': error_message or '',
                'task': self.to_dict(),
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format to facilitate direct return to JSON API."""
        return {
            'task_id': self.task_id,
            'query': self.query,
            'status': self.status,
            'progress': self.progress,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'has_result': bool(self.html_content),
            'report_file_ready': bool(self.report_file_path),
            'report_file_name': self.report_file_name,
            'report_file_path': self.report_file_relative_path or self.report_file_path,
            'state_file_ready': bool(self.state_file_path),
            'state_file_path': self.state_file_relative_path or self.state_file_path,
            'ir_file_ready': bool(self.ir_file_path),
            'ir_file_path': self.ir_file_relative_path or self.ir_file_path,
            'markdown_file_ready': bool(self.markdown_file_path),
            'markdown_file_name': self.markdown_file_name,
            'markdown_file_path': self.markdown_file_relative_path or self.markdown_file_path
        }

    def publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Put any event into the cache and broadcast it. All new logic is accompanied by Chinese instructions.

        Parameters:
            event_type: event name in SSE.
            payload: actual business data."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        event: Dict[str, Any] = {
            'id': 0,
            'type': event_type,
            'task_id': self.task_id,
            'timestamp': timestamp,
            'payload': payload,
        }
        with self._event_lock:
            self.last_event_id += 1
            event['id'] = self.last_event_id
            self.event_history.append(event)
        _broadcast_event(self.task_id, event)

    def history_since(self, last_event_id: Optional[int]) -> List[Dict[str, Any]]:
        """Reissue historical events based on Last-Event-ID to ensure no omissions are missed when disconnected and reconnected.

        Parameters:
            last_event_id: The last event ID recorded by the SSE client.

        Return:
            list[dict]: List of events starting from last_event_id."""
        with self._event_lock:
            if last_event_id is None:
                return list(self.event_history)
            return [evt for evt in self.event_history if evt['id'] > last_event_id]


def check_engines_ready() -> Dict[str, Any]:
    """Check whether all three sub-engines have new files.

    Call the ReportAgent's benchmark detection logic, and attach the forum log existence,
    It is the pre-check of /status and /generate."""
    directories = {
        'insight': 'insight_engine_streamlit_reports',
        'media': 'media_engine_streamlit_reports',
        'query': 'query_engine_streamlit_reports'
    }

    forum_log_path = 'logs/forum.log'

    if not report_agent:
        return {
            'ready': False,
            'error': 'Report Engine未初始化'
        }

    return report_agent.check_input_files(
        directories['insight'],
        directories['media'],
        directories['query'],
        forum_log_path
    )


def run_report_generation(task: ReportTask, query: str, custom_template: str = ""):
    """Run report generation in a background thread.

    Including: check input → load document → call ReportAgent → persist output →
    Push phased events. If an error occurs, the status will be automatically pushed and written.

    Parameters:
        task: This task object holds the event queue internally.
        query: report subject.
        custom_template: Optional custom template string."""
    global current_task

    try:
        # Encapsulate push logic in a local closure to facilitate passing it to ReportAgent
        def stream_handler(event_type: str, payload: Dict[str, Any]):
            """All stage events are distributed through the same interface to ensure consistent logs."""
            task.publish_event(event_type, payload)
            # If the event contains progress information, update the task progress synchronously
            if event_type == 'progress' and 'progress' in payload:
                task.update_status("running", payload['progress'])

        task.update_status("running", 5)
        task.publish_event('stage', {'message': '任务已启动，正在检查输入文件', 'stage': 'prepare'})

        # Check input file
        check_result = check_engines_ready()
        if not check_result['ready']:
            task.update_status("error", 0, f"Input file not ready: {check_result.get('missing_files', [])}")
            return

        task.publish_event('stage', {
            'message': '输入文件检查通过，准备载入内容',
            'stage': 'io_ready',
            'files': check_result.get('latest_files', {})
        })

        # Load input file
        content = report_agent.load_input_files(check_result['latest_files'])
        task.publish_event('stage', {'message': '源数据加载完成，启动生成流程', 'stage': 'data_loaded'})

        # Generate reports (with full retry to alleviate instantaneous network jitter)
        for attempt in range(1, 3):
            try:
                task.publish_event('stage', {
                    'message': f'正在调用ReportAgent生成报告（第{attempt}次尝试）',
                    'stage': 'agent_running',
                    'attempt': attempt
                })
                generation_result = report_agent.generate_report(
                    query=query,
                    reports=content['reports'],
                    forum_logs=content['forum_logs'],
                    custom_template=custom_template,
                    save_report=True,
                    stream_handler=stream_handler
                )
                break
            except ChapterJsonParseError as err:
                hint_message = "Try to replace the Report Engine API with LLM, which has stronger computing power and longer context."
                task.publish_event('warning', {
                    'message': hint_message,
                    'stage': 'agent_running',
                    'attempt': attempt,
                    'reason': 'chapter_json_parse',
                    'error': str(err),
                    'task': task.to_dict(),
                })
                # Old logic: Restart Report Engine after JSON parsing failure
                # backoff = min(5 * attempt, 15)
                # task.publish_event('stage', {
                # 'message': f'Retry the build task after {backoff} seconds',
                #     'stage': 'retry_wait',
                #     'wait_seconds': backoff
                # })
                # time.sleep(backoff)
                raise ChapterJsonParseError(hint_message) from err
            except Exception as err:
                # Push errors to the front end immediately to facilitate observation of retry strategies
                task.publish_event('warning', {
                    'message': f'ReportAgent执行失败: {str(err)}',
                    'stage': 'agent_running',
                    'attempt': attempt
                })
                if attempt == 2:
                    raise
                # Simple exponential backoff to prevent frequent triggering of current limit (unit seconds)
                backoff = min(5 * attempt, 15)
                task.publish_event('stage', {
                    'message': f'{backoff} 秒后重试生成任务',
                    'stage': 'retry_wait',
                    'wait_seconds': backoff
                })
                time.sleep(backoff)

        if isinstance(generation_result, dict):
            html_report = generation_result.get('html_content', '')
        else:
            html_report = generation_result

        task.publish_event('stage', {'message': '报告生成完毕，准备持久化', 'stage': 'persist'})

        # Save results
        task.html_content = html_report
        if isinstance(generation_result, dict):
            task.report_file_path = generation_result.get('report_filepath', '')
            task.report_file_relative_path = generation_result.get('report_relative_path', '')
            task.report_file_name = generation_result.get('report_filename', '')
            task.state_file_path = generation_result.get('state_filepath', '')
            task.state_file_relative_path = generation_result.get('state_relative_path', '')
            task.ir_file_path = generation_result.get('ir_filepath', '')
            task.ir_file_relative_path = generation_result.get('ir_relative_path', '')
        task.publish_event('html_ready', {
            'message': 'HTML渲染完成，可刷新预览',
            'report_file': task.report_file_relative_path or task.report_file_path,
            'state_file': task.state_file_relative_path or task.state_file_path,
            'task': task.to_dict(),
        })
        task.update_status("completed", 100)
        task.publish_event('completed', {
            'message': '任务完成',
            'duration_seconds': (task.updated_at - task.created_at).total_seconds(),
            'report_file': task.report_file_relative_path or task.report_file_path,
            'task': task.to_dict(),
        })

    except Exception as e:
        logger.exception(f"An error occurred during report generation: {str(e)}")
        task.update_status("error", 0, str(e))
        task.publish_event('error', {
            'message': str(e),
            'stage': 'failed',
            'task': task.to_dict(),
        })
        # Only clean up tasks on error
        with task_lock:
            if current_task and current_task.task_id == task.task_id:
                current_task = None


@report_bp.route('/status', methods=['GET'])
def get_status():
    """Get Report Engine status, including engine readiness and current task information.

    Return:
        Response: JSON structure contains initialized/engines_ready/current tasks, etc."""
    try:
        engines_status = check_engines_ready()

        return jsonify({
            'success': True,
            'initialized': report_agent is not None,
            'engines_ready': engines_status['ready'],
            'files_found': engines_status.get('files_found', []),
            'missing_files': engines_status.get('missing_files', []),
            'current_task': current_task.to_dict() if current_task else None
        })
    except Exception as e:
        logger.exception(f"Failed to obtain Report Engine status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/generate', methods=['POST'])
def generate_report():
    """Start generating the report.

    Responsible for queuing, creating background threads, clearing logs and returning SSE addresses.

    Request body:
        query: report subject (optional).
        custom_template: Custom template string (optional).

    Return:
        Response: JSON, including task_id and SSE stream url."""
    global current_task

    try:
        # Check if any tasks are running
        with task_lock:
            if current_task and current_task.status == "running":
                return jsonify({
                    'success': False,
                    'error': '已有报告生成任务在运行中',
                    'current_task': current_task.to_dict()
                }), 400

            # If there is a completed task, clean it up
            if current_task and current_task.status in ["completed", "error"]:
                current_task = None

        # Get request parameters
        data = request.get_json() or {}
        if not isinstance(data, dict):
            logger.warning("generate_report received non-object JSON payload, original content ignored")
            data = {}
        query = data.get('query', '智能舆情分析报告')
        custom_template = data.get('custom_template', '')

        # Clear log files
        clear_report_log()

        # Check whether the Report Engine is initialized
        if not report_agent:
            return jsonify({
                'success': False,
                'error': 'Report Engine未初始化'
            }), 500

        # Check if the input file is ready
        engines_status = check_engines_ready()
        if not engines_status['ready']:
            return jsonify({
                'success': False,
                'error': '输入文件未准备就绪',
                'missing_files': engines_status.get('missing_files', [])
            }), 400

        # Create new task
        task_id = f"report_{int(time.time())}"
        task = ReportTask(query, task_id, custom_template)

        with task_lock:
            current_task = task
            tasks_registry[task_id] = task
            _prune_task_history_locked()

        # Inform the front-end that tasks have been queued by actively pushing the pending event
        task.publish_event(
            'status',
            {
                'status': task.status,
                'progress': task.progress,
                'message': '任务已排队，等待资源空闲',
                'task': task.to_dict(),
            }
        )

        # Run report generation in a background thread
        thread = threading.Thread(
            target=run_report_generation,
            args=(task, query, custom_template),
            daemon=True
        )
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '报告生成已启动',
            'task': task.to_dict(),
            'stream_url': f"/api/report/stream/{task_id}"
        })

    except Exception as e:
        logger.exception(f"Failed to start generating report: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id: str):
    """Get the report generation progress, and return a completion status if the task is cleared.

    Parameters:
        task_id: unique identifier of the task.

    Return:
        Response: JSON contains the current status of the task."""
    try:
        task = _get_task(task_id)
        if not task:
            # If the task does not exist, it may be that the history record has been cleared and a completion status is returned.
            return jsonify({
                'success': True,
                'task': {
                    'task_id': task_id,
                    'status': 'completed',
                    'progress': 100,
                    'error_message': '',
                    'has_result': True,
                    'report_file_ready': False,
                    'report_file_name': '',
                    'report_file_path': '',
                    'state_file_ready': False,
                    'state_file_path': ''
                }
            })

        return jsonify({
            'success': True,
            'task': task.to_dict()
        })

    except Exception as e:
        logger.exception(f"Failed to get report generation progress: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/stream/<task_id>', methods=['GET'])
def stream_task(task_id: str):
    """Real-time push interface based on SSE.

    - Automatically reissue historical events after Last-Event-ID;
    - Send heartbeats periodically to prevent agent interruption;
    - Automatically log out of the monitor after the task is completed.

    Parameters:
        task_id: unique identifier of the task.

    Return:
        Response: `text/event-stream` type response."""
    task = _get_task(task_id)
    if not task:
        return jsonify({'success': False, 'error': '任务不存在'}), 404

    last_event_header = request.headers.get('Last-Event-ID')
    try:
        last_event_id = int(last_event_header) if last_event_header else None
    except ValueError:
        last_event_id = None

    def client_disconnected() -> bool:
        """Detect whether the client has been disconnected as early as possible to avoid continuing to write and trigger BrokenPipe.

        The eventlet on Windows will throw a ConnectionAbortedError when closing the connection.
        Exiting the generator early can reduce meaningless logging."""
        try:
            env_input = request.environ.get('wsgi.input')
            return bool(getattr(env_input, 'closed', False))
        except Exception:
            return False

    def event_generator():
        """SSE event generator.

        - Responsible for registering and consuming the event queue of the corresponding task;
        - Play back historical events first and then continue to monitor real-time events;
        - Send heartbeats periodically and automatically log off the listener after the task is completed."""
        queue = _register_stream(task_id)
        last_data_ts = time.time()
        try:
            # In the scenario of disconnection and reconnection, historical events are reissued first to ensure consistent interface status.
            history = task.history_since(last_event_id)
            for event in history:
                yield _format_sse(event)
                if event.get('type') != 'heartbeat':
                    last_data_ts = time.time()

            finished = task.status in STREAM_TERMINAL_STATUSES
            while True:
                if finished:
                    break
                if client_disconnected():
                    logger.info(f"SSE client has been disconnected and stopped pushing: {task_id}")
                    break
                event = None
                try:
                    event = queue.get(timeout=STREAM_HEARTBEAT_INTERVAL)
                except Empty:
                    if task.status in STREAM_TERMINAL_STATUSES:
                        logger.info(f"Task {task_id} has ended and there are no new events. SSE automatically shuts down.")
                        break
                    heartbeat = {
                        'id': f"hb-{int(time.time() * 1000)}",
                        'type': 'heartbeat',
                        'task_id': task_id,
                        'timestamp': datetime.utcnow().isoformat() + 'Z',
                        'payload': {'status': task.status}
                    }
                    event = heartbeat
                if event is None:
                    logger.warning(f"SSE push event acquisition failed (task {task_id}) and ended early")
                    break

                try:
                    yield _format_sse(event)
                    if event.get('type') != 'heartbeat':
                        last_data_ts = time.time()
                except GeneratorExit:
                    logger.info(f"SSE generator shuts down, stopping task {task_id} push")
                    break
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as exc:
                    logger.warning(f"SSE connection interrupted by client (task {task_id}): {exc}")
                    break
                except Exception as exc:
                    event_type = event.get('type') if isinstance(event, dict) else 'unknown'
                    logger.exception(f"SSE push failed (task {task_id}, event {event_type}): {exc}")
                    break

                if event.get('type') in ("completed", "error", "cancelled"):
                    finished = True
                else:
                    finished = finished or task.status in STREAM_TERMINAL_STATUSES

                # The final state can be kept alive for a maximum period of time to prevent the front end from ending but the background loop has not exited.
                if task.status in STREAM_TERMINAL_STATUSES:
                    idle_for = time.time() - last_data_ts
                    if idle_for > STREAM_IDLE_TIMEOUT:
                        logger.info(f"Task {task_id} is finalized and idle for {int(idle_for)}s, and SSE is actively closed.")
                        break
        finally:
            _unregister_stream(task_id, queue)

    response = Response(
        stream_with_context(event_generator()),
        mimetype='text/event-stream'
    )
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@report_bp.route('/result/<task_id>', methods=['GET'])
def get_result(task_id: str):
    """Get report generation results.

    Parameters:
        task_id: task ID.

    Return:
        Response: JSON, including HTML preview and file path."""
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        if task.status != "completed":
            return jsonify({
                'success': False,
                'error': '报告尚未完成',
                'task': task.to_dict()
            }), 400

        return Response(
            task.html_content,
            mimetype='text/html'
        )

    except Exception as e:
        logger.exception(f"Failed to obtain report generation results: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/result/<task_id>/json', methods=['GET'])
def get_result_json(task_id: str):
    """Get report generation results (JSON format)"""
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        if task.status != "completed":
            return jsonify({
                'success': False,
                'error': '报告尚未完成',
                'task': task.to_dict()
            }), 400

        return jsonify({
            'success': True,
            'task': task.to_dict(),
            'html_content': task.html_content
        })

    except Exception as e:
        logger.exception(f"Failed to obtain report generation results: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/download/<task_id>', methods=['GET'])
def download_report(task_id: str):
    """Download the generated report HTML file.

    Parameters:
        task_id: task ID.

    Return:
        Response: The attachment download response of the HTML file."""
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        if task.status != "completed" or not task.report_file_path:
            return jsonify({
                'success': False,
                'error': '报告尚未完成或尚未保存'
            }), 400

        if not os.path.exists(task.report_file_path):
            return jsonify({
                'success': False,
                'error': '报告文件不存在或已被删除'
            }), 404

        download_name = task.report_file_name or os.path.basename(task.report_file_path)
        return send_file(
            task.report_file_path,
            mimetype='text/html',
            as_attachment=True,
            download_name=download_name
        )

    except Exception as e:
        logger.exception(f"Failed to download report: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id: str):
    """Cancel the report generation task.

    Parameters:
        task_id: The task ID that needs to be canceled.

    Return:
        Response: JSON, containing cancellation results or error information."""
    global current_task

    try:
        with task_lock:
            if current_task and current_task.task_id == task_id:
                if current_task.status == "running":
                    current_task.update_status("cancelled", 0, "User cancels task")
                    current_task.publish_event('cancelled', {
                        'message': '任务被用户主动终止',
                        'task': current_task.to_dict(),
                    })
                current_task = None
            task = tasks_registry.get(task_id)
            if task and task.status == 'running':
                task.update_status("cancelled", task.progress, "User cancels task")
                task.publish_event('cancelled', {
                    'message': '任务被用户主动终止',
                    'task': task.to_dict(),
                })

                return jsonify({
                    'success': True,
                    'message': '任务已取消'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': '任务不存在或无法取消'
                }), 404

    except Exception as e:
        logger.exception(f"Failed to cancel report generation task: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/templates', methods=['GET'])
def get_templates():
    """Get the list of available templates to facilitate the front-end display of optional Markdown skeletons.

    Return:
        Response: JSON, listing template name/description/size."""
    try:
        if not report_agent:
            return jsonify({
                'success': False,
                'error': 'Report Engine未初始化'
            }), 500

        template_dir = settings.TEMPLATE_DIR
        templates = []

        if os.path.exists(template_dir):
            for filename in os.listdir(template_dir):
                if filename.endswith('.md'):
                    template_path = os.path.join(template_dir, filename)
                    try:
                        with open(template_path, 'r', encoding='utf-8') as f:
                            content = f.read()

                        templates.append({
                            'name': filename.replace('.md', ''),
                            'filename': filename,
                            'description': content.split('\n')[0] if content else '无描述',
                            'size': len(content)
                        })
                    except Exception as e:
                        logger.exception(f"Failed to read template {filename}: {str(e)}")

        return jsonify({
            'success': True,
            'templates': templates,
            'template_dir': template_dir
        })

    except Exception as e:
        logger.exception(f"Failed to get list of available templates: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Error handling
@report_bp.errorhandler(404)
def not_found(error):
    """404 back-up processing: ensure that the interface uniformly returns the JSON structure"""
    logger.exception(f"API endpoint does not exist: {str(error)}")
    return jsonify({
        'success': False,
        'error': 'API端点不存在'
    }), 404


@report_bp.errorhandler(500)
def internal_error(error):
    """500 cover-up processing: catching exceptions that are not actively caught"""
    logger.exception(f"Server internal error: {str(error)}")
    return jsonify({
        'success': False,
        'error': '服务器内部错误'
    }), 500


def clear_report_log():
    """Clear the report.log file so that new tasks can only view this run log.

    Return:
        None"""
    try:
        log_file = settings.LOG_FILE

        # [Fix] Use truncate instead of reopening to avoid file handle conflicts with logger
        # Open append mode, then truncate, keeping the file handle valid
        with open(log_file, 'r+', encoding='utf-8') as f:
            f.truncate(0)  # Clear file contents without closing file
            f.flush()      # Refresh now

        logger.info(f"Log file cleared: {log_file}")
    except FileNotFoundError:
        # File does not exist, create empty file
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('')
            logger.info(f"Create log file: {log_file}")
        except Exception as e:
            logger.exception(f"Failed to create log file: {str(e)}")
    except Exception as e:
        logger.exception(f"Failed to clear log file: {str(e)}")


@report_bp.route('/log', methods=['GET'])
def get_report_log():
    """Get the report.log content and remove the blanks line by line and return it.

    [Fix] Optimize large file reading, add error handling and file locking

    Return:
        Response: JSON, containing array of latest log lines."""
    try:
        log_file = settings.LOG_FILE

        if not os.path.exists(log_file):
            return jsonify({
                'success': True,
                'log_lines': []
            })

        # [Fix] Check file size to avoid memory problems caused by reading too large files
        file_size = os.path.getsize(log_file)
        max_size = 10 * 1024 * 1024  # 10MB limit

        if file_size > max_size:
            # File too large, only last 10MB read
            with open(log_file, 'rb') as f:
                f.seek(-max_size, 2)  # 10MB forward from the end of the file
                # Skip the first line which may be incomplete
                f.readline()
                content = f.read().decode('utf-8', errors='replace')
            lines = content.splitlines()
            logger.warning(f"Log file too large ({file_size} bytes), only last {max_size} bytes returned")
        else:
            # Normal size, read in full
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

        # Clean newlines and blank lines at the end of lines
        log_lines = [line.rstrip('\n\r') for line in lines if line.strip()]

        return jsonify({
            'success': True,
            'log_lines': log_lines
        })

    except PermissionError as e:
        logger.error(f"Insufficient permission to read log: {str(e)}")
        return jsonify({
            'success': False,
            'error': '读取日志权限不足'
        }), 403
    except UnicodeDecodeError as e:
        logger.error(f"Log file encoding error: {str(e)}")
        return jsonify({
            'success': False,
            'error': '日志文件编码错误'
        }), 500
    except Exception as e:
        logger.exception(f"Failed to read log: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'读取日志失败: {str(e)}'
        }), 500


@report_bp.route('/log/clear', methods=['POST'])
def clear_log():
    """Clear the log manually and provide a REST entrance for one-click reset of the front end.

    Return:
        Response: JSON, marking whether the cleaning was successful."""
    try:
        clear_report_log()
        return jsonify({
            'success': True,
            'message': '日志已清空'
        })
    except Exception as e:
        logger.exception(f"Failed to clear log: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'清空日志失败: {str(e)}'
        }), 500


@report_bp.route('/export/md/<task_id>', methods=['GET'])
def export_markdown(task_id: str):
    """Export the report to Markdown format.

    Call MarkdownRenderer based on the saved Document IR, generate the file and return the download."""
    try:
        task = tasks_registry.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        if task.status != 'completed':
            return jsonify({
                'success': False,
                'error': f'任务未完成，当前状态: {task.status}'
            }), 400

        if not task.ir_file_path or not os.path.exists(task.ir_file_path):
            return jsonify({
                'success': False,
                'error': 'IR文件不存在，无法生成Markdown'
            }), 404

        with open(task.ir_file_path, 'r', encoding='utf-8') as f:
            document_ir = json.load(f)

        from .renderers import MarkdownRenderer
        renderer = MarkdownRenderer()
        # Pass in ir_file_path, the repaired chart will be automatically saved to the IR file
        markdown_text = renderer.render(document_ir, ir_file_path=task.ir_file_path)

        metadata = document_ir.get('metadata') if isinstance(document_ir, dict) else {}
        topic = (metadata or {}).get('topic') or (metadata or {}).get('title') or (metadata or {}).get('query') or task.query
        safe_topic = _safe_filename_segment(topic or 'report')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"report_{safe_topic}_{timestamp}.md"

        output_dir = Path(settings.OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / filename
        md_path.write_text(markdown_text, encoding='utf-8')

        task.markdown_file_path = str(md_path.resolve())
        task.markdown_file_relative_path = os.path.relpath(task.markdown_file_path, os.getcwd())
        task.markdown_file_name = filename

        logger.info(f"Export Markdown is completed: {md_path}")

        return send_file(
            task.markdown_file_path,
            mimetype='text/markdown',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.exception(f"Failed to export Markdown: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'导出Markdown失败: {str(e)}'
        }), 500


@report_bp.route('/export/pdf/<task_id>', methods=['GET'])
def export_pdf(task_id: str):
    """Export reports to PDF format.

    Generate optimized PDF from IR JSON files, supporting automatic layout adjustment.

    Parameters:
        task_id: task ID

    Query parameters:
        optimize: whether to enable layout optimization (default true)

    Return:
        Response: PDF file stream or error message"""
    try:
        # Detecting Pango dependencies
        from .utils.dependency_check import check_pango_available
        pango_available, pango_message = check_pango_available()
        if not pango_available:
            return jsonify({
                'success': False,
                'error': 'PDF 导出功能不可用：缺少系统依赖',
                'details': '请查看根目录 README.md “源码启动”的第二步（PDF 导出依赖）了解安装方法',
                'help_url': 'https://github.com/666ghj/BettaFish# 2-Install-pdf-Export required system dependencies optional',
                'system_message': pango_message
            }), 503

        # Get task information
        task = tasks_registry.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        # Check if the task is completed
        if task.status != 'completed':
            return jsonify({
                'success': False,
                'error': f'任务未完成，当前状态: {task.status}'
            }), 400

        # Get IR file path
        if not task.ir_file_path or not os.path.exists(task.ir_file_path):
            return jsonify({
                'success': False,
                'error': 'IR文件不存在'
            }), 404

        # Read IR data
        with open(task.ir_file_path, 'r', encoding='utf-8') as f:
            document_ir = json.load(f)

        # Check if layout optimization is enabled
        optimize = request.args.get('optimize', 'true').lower() == 'true'

        # Create PDF renderer and generate PDF
        from .renderers import PDFRenderer
        renderer = PDFRenderer()

        logger.info(f"Start exporting PDF, task ID: {task_id}, layout optimization: {optimize}")

        # Generate PDF byte stream
        pdf_bytes = renderer.render_to_bytes(document_ir, optimize_layout=optimize)

        # Confirm download file name
        topic = document_ir.get('metadata', {}).get('topic', 'report')
        pdf_filename = f"report_{topic}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        # Return to PDF file
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{pdf_filename}"',
                'Content-Type': 'application/pdf'
            }
        )

    except Exception as e:
        logger.exception(f"Failed to export PDF: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'导出PDF失败: {str(e)}'
        }), 500


@report_bp.route('/export/pdf-from-ir', methods=['POST'])
def export_pdf_from_ir():
    """Export PDF directly from IR JSON (no task ID required).

    Suitable for scenarios where the front end directly transmits IR data.

    Request body:
        {"document_ir": {...},  // Document IR JSON
            "optimize": true // Whether to enable layout optimization (optional)
        }

    Return:
        Response: PDF file stream or error message"""
    try:
        # Detecting Pango dependencies
        from .utils.dependency_check import check_pango_available
        pango_available, pango_message = check_pango_available()
        if not pango_available:
            return jsonify({
                'success': False,
                'error': 'PDF 导出功能不可用：缺少系统依赖',
                'details': '请查看根目录 README.md “源码启动”的第二步（PDF 导出依赖）了解安装方法',
                'help_url': 'https://github.com/666ghj/BettaFish# 2-Install-pdf-Export required system dependencies optional',
                'system_message': pango_message
            }), 503

        data = request.get_json() or {}
        if not isinstance(data, dict):
            logger.warning("export_pdf_from_ir request body is not a JSON object")
            return jsonify({
                'success': False,
                'error': '请求体必须是JSON对象'
            }), 400

        if not data or 'document_ir' not in data:
            return jsonify({
                'success': False,
                'error': '缺少document_ir参数'
            }), 400

        document_ir = data['document_ir']
        optimize = data.get('optimize', True)

        # Create PDF renderer and generate PDF
        from .renderers import PDFRenderer
        renderer = PDFRenderer()

        logger.info(f"Export PDF directly from IR, layout optimization: {optimize}")

        # Generate PDF byte stream
        pdf_bytes = renderer.render_to_bytes(document_ir, optimize_layout=optimize)

        # Confirm download file name
        topic = document_ir.get('metadata', {}).get('topic', 'report')
        pdf_filename = f"report_{topic}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        # Return to PDF file
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{pdf_filename}"',
                'Content-Type': 'application/pdf'
            }
        )

    except Exception as e:
        logger.exception(f"Exporting PDF from IR failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'导出PDF失败: {str(e)}'
        }), 500
