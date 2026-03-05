"""Built-in image generation tool powered by Google Imagen."""

from __future__ import annotations

import os
from typing import Any

from fim_agent.core.tool.base import BaseTool


class GenerateImageTool(BaseTool):
    """Generate an image from a text prompt using Google Imagen (via Gemini API).

    Requires IMAGE_GEN_API_KEY to be set in the environment.
    The generated image is saved to the uploads directory and the agent
    receives a markdown image link it can embed in its reply.
    """

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def display_name(self) -> str:
        return "Generate Image"

    @property
    def category(self) -> str:
        return "media"

    @property
    def description(self) -> str:
        return (
            "Generate an image from a text description using Google Imagen. "
            "Returns a markdown image link that renders inline in the chat. "
            "Supports aspect ratios: 1:1 (default), 16:9, 9:16, 4:3, 3:4."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed text description of the image to generate.",
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"],
                    "description": "Image aspect ratio. Defaults to 1:1.",
                    "default": "1:1",
                },
            },
            "required": ["prompt"],
        }

    def availability(self) -> tuple[bool, str | None]:
        if not os.environ.get("IMAGE_GEN_API_KEY"):
            return (
                False,
                "Set IMAGE_GEN_API_KEY (Google AI Studio key) in your environment to enable image generation.",
            )
        return True, None

    async def run(self, *, prompt: str, aspect_ratio: str = "1:1") -> str:
        available, reason = self.availability()
        if not available:
            return f"Error: {reason}"

        # Resolve uploads output directory
        uploads_dir = os.environ.get("UPLOADS_DIR", "./uploads")
        output_dir = os.path.join(uploads_dir, "generated")

        from fim_agent.core.image_gen.google import GoogleImageGen

        gen = GoogleImageGen()
        try:
            result = await gen.generate(
                prompt, aspect_ratio=aspect_ratio, output_dir=output_dir
            )
        except Exception as exc:
            return f"Image generation failed: {exc}"

        return (
            f"![Generated Image]({result.url})\n\n"
            f"*Prompt:* {result.prompt}  \n"
            f"*Model:* {result.model}"
        )
