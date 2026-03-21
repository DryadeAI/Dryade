"""Image Generation MCP Server wrapper.

Provides typed Python interface for image generation MCP servers
compatible with Stable Diffusion, ComfyUI, or DALL-E APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry

@dataclass
class ImageData:
    """Single generated image data.

    Attributes:
        base64_data: Base64-encoded image bytes.
        mime_type: MIME type of the image (e.g., "image/png").
        width: Image width in pixels.
        height: Image height in pixels.
    """

    base64_data: str
    mime_type: str = "image/png"
    width: int = 1024
    height: int = 1024

@dataclass
class ImageGenResult:
    """Result from an image generation request.

    Attributes:
        images: List of generated images.
        seed: Seed used for generation (for reproducibility).
        prompt: The prompt that was used.
    """

    images: list[ImageData] = field(default_factory=list)
    seed: int = 0
    prompt: str = ""

class ImageGenServer:
    """Typed wrapper for image generation MCP servers.

    Supports Stable Diffusion WebUI API, ComfyUI, or DALL-E compatible
    endpoints via the MCP HTTP transport.

    Example:
        >>> from core.mcp import get_registry
        >>> registry = get_registry()
        >>> image_gen = ImageGenServer(registry)
        >>> result = image_gen.generate("A sunset over mountains")
        >>> print(f"Generated {len(result.images)} images")
    """

    def __init__(self, registry: MCPRegistry, server_name: str = "image-gen") -> None:
        """Initialize ImageGenServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the image gen server in registry.
        """
        self._registry = registry
        self._server_name = server_name

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        seed: int | None = None,
    ) -> ImageGenResult:
        """Generate images from a text prompt.

        Args:
            prompt: Text description of the desired image.
            negative_prompt: Things to avoid in the generated image.
            width: Output image width in pixels.
            height: Output image height in pixels.
            steps: Number of diffusion steps (higher = better quality, slower).
            seed: Random seed for reproducibility. None for random.

        Returns:
            ImageGenResult with generated images and metadata.

        Raises:
            MCPTransportError: If image generation fails.

        Example:
            >>> result = image_gen.generate(
            ...     prompt="A photorealistic cat wearing a top hat",
            ...     negative_prompt="blurry, low quality",
            ...     width=512,
            ...     height=512,
            ...     steps=20,
            ... )
        """
        args: dict = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
        }
        if seed is not None:
            args["seed"] = seed

        result = self._registry.call_tool(self._server_name, "generate", args)
        return self._parse_result(result, prompt)

    def _parse_result(self, result: MCPToolCallResult, prompt: str) -> ImageGenResult:
        """Parse MCP tool call result into ImageGenResult.

        Extracts image content items and text metadata from the result.

        Args:
            result: Raw MCP tool call result.
            prompt: Original prompt for metadata.

        Returns:
            Parsed ImageGenResult.
        """
        images: list[ImageData] = []
        seed = 0

        for item in result.content:
            if item.type == "image" and item.data:
                images.append(
                    ImageData(
                        base64_data=item.data,
                        mime_type=item.mimeType or "image/png",
                    )
                )
            elif item.type == "text" and item.text:
                # Try to extract seed from text metadata
                import json

                try:
                    meta = json.loads(item.text)
                    if isinstance(meta, dict):
                        seed = meta.get("seed", 0)
                except (json.JSONDecodeError, TypeError):
                    pass

        return ImageGenResult(images=images, seed=seed, prompt=prompt)

    def _extract_text(self, result: MCPToolCallResult) -> str:
        """Extract text content from MCP tool result.

        Args:
            result: MCP tool call result.

        Returns:
            Text content from the first text item, or empty string.
        """
        if result.content:
            for item in result.content:
                if item.type == "text" and item.text:
                    return item.text
        return ""
