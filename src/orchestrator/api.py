"""
Orchestrator REST API

Endpoints for agents to interact with workflow enforcement:
- POST /api/v1/tasks/claim - Claim a task and get phase token
- POST /api/v1/tasks/transition - Request phase transition
- POST /api/v1/tools/execute - Execute tool with permission check
- GET /api/v1/state/snapshot - Get read-only state snapshot
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI, HTTPException, Depends
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except ImportError:
    # Will be installed on Day 6
    FastAPI = None
    HTTPException = None
    BaseModel = None

from .enforcement import WorkflowEnforcement
from .state import state_manager
from .events import event_bus, EventTypes


# ============================================================================
# REQUEST/RESPONSE MODELS (Pydantic)
# ============================================================================

if BaseModel:
    class ClaimTaskRequest(BaseModel):
        """Request to claim a task"""
        agent_id: str
        capabilities: Optional[List[str]] = None

    class ClaimTaskResponse(BaseModel):
        """Response with task and phase token"""
        task: Dict[str, Any]
        phase_token: str
        phase: str

    class TransitionRequest(BaseModel):
        """Request to transition phases"""
        task_id: str
        current_phase: str
        target_phase: str
        phase_token: str
        artifacts: Dict[str, Any]

    class TransitionResponse(BaseModel):
        """Response to transition request"""
        allowed: bool
        new_token: Optional[str] = None
        blockers: List[str] = []

    class ToolExecuteRequest(BaseModel):
        """Request to execute a tool"""
        task_id: str
        phase_token: str
        tool_name: str
        args: Dict[str, Any]

    class ToolExecuteResponse(BaseModel):
        """Response from tool execution"""
        result: Any
        logged: bool = True

    class StateSnapshotResponse(BaseModel):
        """Read-only state snapshot"""
        task_dependencies: List[str]
        completed_tasks: List[str]
        current_phase: str
        blockers: List[str]

    class AuditQueryResponse(BaseModel):
        """Audit log query response"""
        entries: List[Dict[str, Any]]
        total: int

    class AuditStatsResponse(BaseModel):
        """Audit log statistics response"""
        total_entries: int
        total_successes: int
        total_failures: int
        success_rate: float
        tools_used: Dict[str, int]
        phases: Dict[str, int]


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

# Global enforcement engine instance
enforcement: Optional[WorkflowEnforcement] = None

if FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Lifespan event handler for FastAPI application

        Initializes enforcement engine on startup, cleans up on shutdown.
        """
        global enforcement
        # Startup
        workflow_path = Path("agent_workflow.yaml")
        enforcement = WorkflowEnforcement(workflow_path)
        print(f"✓ Loaded workflow from {workflow_path}")
        print(f"✓ Enforcement mode: {enforcement.workflow['enforcement']['mode']}")

        yield

        # Shutdown (cleanup if needed)
        enforcement = None


    app = FastAPI(
        title="Workflow Orchestrator API",
        version="1.0.0",
        description="Workflow enforcement API for parallel agents",
        lifespan=lifespan
    )


    @app.get("/")
    async def root():
        """Health check endpoint"""
        return {"status": "ok", "service": "workflow-orchestrator-api"}


    @app.get("/health")
    async def health():
        """Health check with workflow status"""
        if enforcement is None:
            raise HTTPException(status_code=503, detail="Enforcement engine not initialized")

        return {
            "status": "healthy",
            "workflow_loaded": enforcement.workflow is not None,
            "enforcement_mode": enforcement.workflow["enforcement"]["mode"]
        }


    @app.post("/api/v1/tasks/claim", response_model=ClaimTaskResponse)
    async def claim_task(request: ClaimTaskRequest):
        """
        Claim a task and receive phase token for PLAN phase

        Returns:
            Task details and phase token for PLAN phase
        """
        if enforcement is None:
            raise HTTPException(status_code=503, detail="Enforcement engine not initialized")

        # Generate task ID (in production, this would come from a task queue)
        import uuid
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        # Get first phase from workflow (usually PLAN)
        phases = enforcement.workflow.get("phases", [])
        if not phases:
            raise HTTPException(status_code=500, detail="No phases defined in workflow")

        initial_phase = phases[0]["id"]

        try:
            # Generate phase token for initial phase
            phase_token = enforcement.generate_phase_token(task_id, initial_phase)

            # Register task in state manager
            state_manager.register_task(
                task_id=task_id,
                agent_id=request.agent_id,
                phase=initial_phase,
                dependencies=None  # Could be passed in request if needed
            )

            # Publish task claimed event
            event_bus.publish(EventTypes.TASK_CLAIMED, {
                "task_id": task_id,
                "agent_id": request.agent_id,
                "phase": initial_phase,
                "capabilities": request.capabilities or []
            })

            # Return task details and token
            return ClaimTaskResponse(
                task={
                    "id": task_id,
                    "agent_id": request.agent_id,
                    "capabilities": request.capabilities or [],
                    "assigned_phase": initial_phase
                },
                phase_token=phase_token,
                phase=initial_phase
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate phase token: {str(e)}")


    @app.post("/api/v1/tasks/transition", response_model=TransitionResponse)
    async def request_transition(request: TransitionRequest):
        """
        Request phase transition

        Validates:
        - Phase token
        - Required artifacts
        - Gate blockers

        Returns:
            Allowed status and new token if approved
        """
        if enforcement is None:
            raise HTTPException(status_code=503, detail="Enforcement engine not initialized")

        # Step 1: Verify current phase token
        token_valid = enforcement._verify_phase_token(
            request.phase_token,
            request.task_id,
            request.current_phase
        )

        if not token_valid:
            raise HTTPException(
                status_code=403,
                detail="Invalid or expired phase token"
            )

        # Step 2: Find transition definition
        transition = enforcement._find_transition(
            request.current_phase,
            request.target_phase
        )

        if not transition:
            raise HTTPException(
                status_code=400,
                detail=f"No transition defined from {request.current_phase} to {request.target_phase}"
            )

        # Step 3: Validate required artifacts
        from_phase = enforcement._get_phase(request.current_phase)
        if not from_phase:
            raise HTTPException(
                status_code=400,
                detail=f"Phase not found: {request.current_phase}"
            )

        required_artifacts = from_phase.get("required_artifacts", [])
        if required_artifacts:
            artifacts_valid, artifact_errors = enforcement._validate_artifacts(
                request.artifacts,
                required_artifacts
            )

            if not artifacts_valid:
                # Publish gate blocked event
                event_bus.publish(EventTypes.GATE_BLOCKED, {
                    "task_id": request.task_id,
                    "from_phase": request.current_phase,
                    "to_phase": request.target_phase,
                    "gate_id": "artifact_validation",
                    "blockers": artifact_errors
                })

                return TransitionResponse(
                    allowed=False,
                    new_token=None,
                    blockers=artifact_errors
                )

        # Step 4: Validate gate blockers
        gate_id = transition.get("gate")
        if gate_id:
            gate_passes, gate_blockers = enforcement._validate_gate(
                gate_id,
                request.artifacts
            )

            if not gate_passes:
                # Publish gate blocked event
                event_bus.publish(EventTypes.GATE_BLOCKED, {
                    "task_id": request.task_id,
                    "from_phase": request.current_phase,
                    "to_phase": request.target_phase,
                    "gate_id": gate_id,
                    "blockers": gate_blockers
                })

                return TransitionResponse(
                    allowed=False,
                    new_token=None,
                    blockers=gate_blockers
                )

        # Step 5: Transition approved - generate new phase token
        try:
            new_token = enforcement.generate_phase_token(
                request.task_id,
                request.target_phase
            )

            # Update phase in state manager
            state_manager.update_phase(request.task_id, request.target_phase)

            # Publish gate passed event
            if gate_id:
                event_bus.publish(EventTypes.GATE_PASSED, {
                    "task_id": request.task_id,
                    "from_phase": request.current_phase,
                    "to_phase": request.target_phase,
                    "gate_id": gate_id
                })

            # Publish phase transition event
            event_bus.publish(EventTypes.TASK_TRANSITIONED, {
                "task_id": request.task_id,
                "from_phase": request.current_phase,
                "to_phase": request.target_phase,
                "artifacts": list(request.artifacts.keys())
            })

            return TransitionResponse(
                allowed=True,
                new_token=new_token,
                blockers=[]
            )

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate new phase token: {str(e)}"
            )


    @app.post("/api/v1/tools/execute", response_model=ToolExecuteResponse)
    async def execute_tool(request: ToolExecuteRequest):
        """
        Execute tool with permission check

        Checks:
        - Phase token valid
        - Tool allowed in current phase
        - Tool constraints satisfied

        Returns:
            Tool execution result
        """
        if enforcement is None:
            raise HTTPException(status_code=503, detail="Enforcement engine not initialized")

        # Decode token to get phase (without full verification to get phase info)
        try:
            import jwt
            payload = jwt.decode(
                request.phase_token,
                enforcement.jwt_secret,
                algorithms=["HS256"]
            )
            current_phase = payload.get("phase")
            task_id = payload.get("task_id")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=403, detail="Invalid or malformed phase token")

        # Verify token matches task
        if task_id != request.task_id:
            raise HTTPException(
                status_code=403,
                detail="Token task_id does not match request task_id"
            )

        # Check if tool is forbidden in current phase
        if enforcement.is_tool_forbidden(current_phase, request.tool_name):
            allowed_tools = enforcement.get_allowed_tools(current_phase)
            raise HTTPException(
                status_code=403,
                detail=f"Tool '{request.tool_name}' not allowed in phase '{current_phase}'. Allowed tools: {allowed_tools}"
            )

        # Execute tool using tool registry
        from .tools import tool_registry, ToolExecutionError
        from .audit import audit_logger
        import time

        start_time = time.time()
        success = False
        result = None
        error_msg = None

        try:
            result = tool_registry.execute(request.tool_name, request.args)
            success = True

            # Log successful execution
            duration_ms = (time.time() - start_time) * 1000
            audit_logger.log_tool_execution(
                task_id=request.task_id,
                phase=current_phase,
                tool_name=request.tool_name,
                args=request.args,
                result=result,
                duration_ms=duration_ms,
                success=True
            )

            # Publish tool execution event
            event_bus.publish(EventTypes.TOOL_EXECUTED, {
                "task_id": request.task_id,
                "phase": current_phase,
                "tool_name": request.tool_name,
                "success": True,
                "duration_ms": duration_ms
            })

            return ToolExecuteResponse(
                result=result,
                logged=True
            )

        except ToolExecutionError as e:
            error_msg = str(e)
            duration_ms = (time.time() - start_time) * 1000

            # Log failed execution
            audit_logger.log_tool_execution(
                task_id=request.task_id,
                phase=current_phase,
                tool_name=request.tool_name,
                args=request.args,
                duration_ms=duration_ms,
                success=False,
                error=error_msg
            )

            # Publish tool execution event (failed)
            event_bus.publish(EventTypes.TOOL_EXECUTED, {
                "task_id": request.task_id,
                "phase": current_phase,
                "tool_name": request.tool_name,
                "success": False,
                "duration_ms": duration_ms,
                "error": error_msg
            })

            raise HTTPException(
                status_code=400,
                detail=f"Tool execution failed: {error_msg}"
            )

        except Exception as e:
            error_msg = str(e)
            duration_ms = (time.time() - start_time) * 1000

            # Log unexpected error
            audit_logger.log_tool_execution(
                task_id=request.task_id,
                phase=current_phase,
                tool_name=request.tool_name,
                args=request.args,
                duration_ms=duration_ms,
                success=False,
                error=f"Unexpected error: {error_msg}"
            )

            # Publish tool execution event (unexpected error)
            event_bus.publish(EventTypes.TOOL_EXECUTED, {
                "task_id": request.task_id,
                "phase": current_phase,
                "tool_name": request.tool_name,
                "success": False,
                "duration_ms": duration_ms,
                "error": f"Unexpected error: {error_msg}"
            })

            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error during tool execution: {error_msg}"
            )


    @app.get("/api/v1/state/snapshot", response_model=StateSnapshotResponse)
    async def get_state_snapshot(phase_token: str):
        """
        Get read-only state snapshot

        Filters state to show only:
        - Tasks the agent depends on
        - Current phase info
        - Blockers

        Args:
            phase_token: JWT token to verify access

        Returns:
            Filtered state snapshot
        """
        if enforcement is None:
            raise HTTPException(status_code=503, detail="Enforcement engine not initialized")

        # Verify token is valid
        try:
            import jwt
            payload = jwt.decode(
                phase_token,
                enforcement.jwt_secret,
                algorithms=["HS256"]
            )
            current_phase = payload.get("phase")
            task_id = payload.get("task_id")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=403, detail="Invalid or expired phase token")

        # Get state snapshot from state manager
        snapshot = state_manager.get_snapshot(task_id)

        return StateSnapshotResponse(
            task_dependencies=snapshot["task_dependencies"],
            completed_tasks=snapshot["completed_tasks"],
            current_phase=snapshot["current_phase"],
            blockers=snapshot["blockers"]
        )


    @app.get("/api/v1/audit/query", response_model=AuditQueryResponse)
    async def query_audit_log(
        task_id: Optional[str] = None,
        phase: Optional[str] = None,
        tool_name: Optional[str] = None,
        success: Optional[bool] = None,
        limit: Optional[int] = 100
    ):
        """
        Query audit log entries

        Args:
            task_id: Filter by task ID
            phase: Filter by phase
            tool_name: Filter by tool name
            success: Filter by success status
            limit: Maximum number of entries

        Returns:
            Matching audit log entries
        """
        from .audit import audit_logger

        entries = audit_logger.query(
            task_id=task_id,
            phase=phase,
            tool_name=tool_name,
            success=success,
            limit=limit
        )

        return AuditQueryResponse(
            entries=entries,
            total=len(entries)
        )


    @app.get("/api/v1/audit/recent", response_model=AuditQueryResponse)
    async def get_recent_audit_entries(count: int = 10):
        """
        Get most recent audit log entries

        Args:
            count: Number of entries to return

        Returns:
            Recent audit log entries (newest first)
        """
        from .audit import audit_logger

        entries = audit_logger.get_recent(count=count)

        return AuditQueryResponse(
            entries=entries,
            total=len(entries)
        )


    @app.get("/api/v1/audit/stats", response_model=AuditStatsResponse)
    async def get_audit_stats():
        """
        Get audit log statistics

        Returns:
            Audit log statistics including success rates and tool usage
        """
        from .audit import audit_logger

        stats = audit_logger.get_stats()

        return AuditStatsResponse(**stats)


# ============================================================================
# SERVER STARTUP (for development)
# ============================================================================

def start_server(host: str = "localhost", port: int = 8000):
    """
    Start the orchestrator API server

    Args:
        host: Host to bind to
        port: Port to bind to
    """
    if FastAPI is None:
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn")

    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Orchestrator API Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run server on")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    args = parser.parse_args()
    start_server(host=args.host, port=args.port)
