"""
MCP Gateway Server

FastAPI server for managing MCP server containers with Docker.
Provides resource isolation, network isolation, and lifecycle management.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import docker
import yaml
from docker.errors import APIError, DockerException, NotFound
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration Models
# =============================================================================

class ResourceLimits(BaseModel):
    """Resource limits for MCP server containers."""

    cpu_limit: float = Field(default=1.0, description="CPU cores limit")
    memory_limit: str = Field(default="2g", description="Memory limit (e.g., 2g)")
    memory_reservation: str = Field(default="512m", description="Memory soft limit")
    pids_limit: int = Field(default=100, description="Max processes")

class ServerRequest(BaseModel):
    """Request to start an MCP server container."""

    name: str = Field(..., description="Unique server name")
    image: str = Field(..., description="Docker image to use")
    command: list[str] | None = Field(default=None, description="Container command")
    environment: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    resources: ResourceLimits | None = Field(default=None, description="Resource limits")
    model_path: str | None = Field(default=None, description="Path to model files")

class ServerStatus(BaseModel):
    """Status of an MCP server container."""

    name: str
    container_id: str
    status: str
    health: str | None = None
    ports: dict[str, str] = Field(default_factory=dict)

class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    docker_connected: bool
    active_servers: int

# =============================================================================
# Gateway Server
# =============================================================================

class GatewayServer:
    """
    MCP Gateway Server for container orchestration.

    Manages MCP server containers with:
    - Resource isolation (1 CPU, 2GB memory default)
    - Network isolation via dedicated network
    - Read-only model file mounts
    - Container lifecycle management
    """

    def __init__(self, config_path: str | None = None):
        """Initialize the gateway server."""
        self.config_path = config_path or os.environ.get(
            "CONFIG_PATH", "/app/config/mcp_gateway.yaml"
        )
        self.config = self._load_config()
        self.docker_client: docker.DockerClient | None = None
        self.network_name = (
            self.config.get("gateway", {}).get("network", {}).get("name", "mcp-servers")
        )
        self._servers: dict[str, str] = {}  # name -> container_id

    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        config_path = Path(self.config_path)
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f)
        logger.warning(f"Config file not found: {config_path}, using defaults")
        return self._default_config()

    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            "gateway": {
                "host": "0.0.0.0",
                "port": 8090,
                "network": {"name": "mcp-servers", "driver": "bridge"},
            },
            "resource_defaults": {
                "cpu_limit": 1,
                "memory_limit": "2g",
                "memory_reservation": "512m",
                "pids_limit": 100,
            },
        }

    def connect(self) -> bool:
        """Connect to Docker daemon."""
        try:
            self.docker_client = docker.from_env()
            self.docker_client.ping()
            logger.info("Connected to Docker daemon")
            return True
        except DockerException as e:
            logger.error(f"Failed to connect to Docker: {e}")
            return False

    def ensure_network(self) -> bool:
        """Ensure the MCP servers network exists."""
        if not self.docker_client:
            return False

        try:
            self.docker_client.networks.get(self.network_name)
            logger.info(f"Network '{self.network_name}' already exists")
            return True
        except NotFound:
            try:
                self.docker_client.networks.create(
                    self.network_name,
                    driver="bridge",
                    labels={"managed-by": "mcp-gateway"},
                )
                logger.info(f"Created network '{self.network_name}'")
                return True
            except APIError as e:
                logger.error(f"Failed to create network: {e}")
                return False

    def _get_resource_limits(self, custom: ResourceLimits | None = None) -> dict:
        """Get resource limits for container, using defaults if not specified."""
        defaults = self.config.get("resource_defaults", {})
        limits = custom or ResourceLimits()

        return {
            "nano_cpus": int(limits.cpu_limit * 1e9),
            "mem_limit": limits.memory_limit or defaults.get("memory_limit", "2g"),
            "mem_reservation": limits.memory_reservation
            or defaults.get("memory_reservation", "512m"),
            "pids_limit": limits.pids_limit or defaults.get("pids_limit", 100),
        }

    def start_server(self, request: ServerRequest) -> ServerStatus:
        """
        Start an MCP server container.

        Creates a container with:
        - Resource limits (CPU, memory, pids)
        - Network isolation on mcp-servers network
        - Read-only model mounts if specified
        - Security constraints (no new privileges, dropped caps)
        """
        if not self.docker_client:
            raise RuntimeError("Not connected to Docker")

        if request.name in self._servers:
            raise ValueError(f"Server '{request.name}' already exists")

        resource_limits = self._get_resource_limits(request.resources)

        # Build volume mounts
        volumes = {}
        if request.model_path:
            volumes[request.model_path] = {
                "bind": "/models",
                "mode": "ro",  # Read-only mount
            }

        # Security options
        security_opts = self.config.get("security", {})

        try:
            container = self.docker_client.containers.run(
                request.image,
                command=request.command,
                name=f"mcp-{request.name}",
                detach=True,
                network=self.network_name,
                environment=request.environment,
                volumes=volumes,
                # Resource limits
                nano_cpus=resource_limits["nano_cpus"],
                mem_limit=resource_limits["mem_limit"],
                mem_reservation=resource_limits["mem_reservation"],
                pids_limit=resource_limits["pids_limit"],
                # Security settings
                read_only=security_opts.get("read_only_rootfs", True),
                security_opt=["no-new-privileges"]
                if security_opts.get("no_new_privileges", True)
                else [],
                cap_drop=security_opts.get("cap_drop", ["ALL"]),
                # Labels for management
                labels={
                    "managed-by": "mcp-gateway",
                    "mcp-server-name": request.name,
                },
            )

            self._servers[request.name] = container.id
            logger.info(f"Started MCP server '{request.name}' ({container.short_id})")

            return ServerStatus(
                name=request.name,
                container_id=container.short_id,
                status="running",
            )

        except APIError as e:
            logger.error(f"Failed to start server '{request.name}': {e}")
            raise RuntimeError(f"Failed to start server: {e}")

    def stop_server(self, name: str) -> bool:
        """Stop and remove an MCP server container."""
        if not self.docker_client:
            raise RuntimeError("Not connected to Docker")

        container_id = self._servers.get(name)
        if not container_id:
            raise ValueError(f"Server '{name}' not found")

        try:
            container = self.docker_client.containers.get(container_id)
            container.stop(timeout=10)
            container.remove()
            del self._servers[name]
            logger.info(f"Stopped MCP server '{name}'")
            return True
        except NotFound:
            # Container already gone
            if name in self._servers:
                del self._servers[name]
            return True
        except APIError as e:
            logger.error(f"Failed to stop server '{name}': {e}")
            raise RuntimeError(f"Failed to stop server: {e}")

    def get_server_status(self, name: str) -> ServerStatus:
        """Get status of an MCP server container."""
        if not self.docker_client:
            raise RuntimeError("Not connected to Docker")

        container_id = self._servers.get(name)
        if not container_id:
            raise ValueError(f"Server '{name}' not found")

        try:
            container = self.docker_client.containers.get(container_id)
            return ServerStatus(
                name=name,
                container_id=container.short_id,
                status=container.status,
                health=container.attrs.get("State", {}).get("Health", {}).get("Status"),
            )
        except NotFound:
            if name in self._servers:
                del self._servers[name]
            raise ValueError(f"Server '{name}' container not found")

    def list_servers(self) -> list[ServerStatus]:
        """List all managed MCP server containers."""
        if not self.docker_client:
            return []

        servers = []
        for name, _container_id in list(self._servers.items()):
            try:
                status = self.get_server_status(name)
                servers.append(status)
            except ValueError:
                # Container gone, already cleaned up
                pass

        return servers

    def health_check(self) -> HealthResponse:
        """Check gateway health."""
        docker_connected = False
        if self.docker_client:
            try:
                self.docker_client.ping()
                docker_connected = True
            except DockerException:
                pass

        return HealthResponse(
            status="healthy" if docker_connected else "unhealthy",
            docker_connected=docker_connected,
            active_servers=len(self._servers),
        )

# =============================================================================
# FastAPI Application
# =============================================================================

# Global gateway instance
gateway = GatewayServer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("MCP Gateway starting...")
    if not gateway.connect():
        logger.error("Failed to connect to Docker - gateway will be unhealthy")
    else:
        gateway.ensure_network()

    yield

    # Shutdown
    logger.info("MCP Gateway shutting down...")
    for name in list(gateway._servers.keys()):
        try:
            gateway.stop_server(name)
        except Exception as e:
            logger.error(f"Failed to stop server '{name}' during shutdown: {e}")

app = FastAPI(
    title="MCP Gateway",
    description="Docker container orchestration for MCP servers",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return gateway.health_check()

@app.post("/servers", response_model=ServerStatus, status_code=status.HTTP_201_CREATED)
async def start_server(request: ServerRequest):
    """Start a new MCP server container."""
    try:
        return gateway.start_server(request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.delete("/servers/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def stop_server(name: str):
    """Stop and remove an MCP server container."""
    try:
        gateway.stop_server(name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/servers/{name}", response_model=ServerStatus)
async def get_server(name: str):
    """Get status of an MCP server container."""
    try:
        return gateway.get_server_status(name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@app.get("/servers", response_model=list[ServerStatus])
async def list_servers():
    """List all managed MCP server containers."""
    return gateway.list_servers()
