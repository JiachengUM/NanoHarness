"""Model profile types and utilities. An analogy to langchain's ModelProfile.
See https://docs.langchain.com/oss/python/langchain/models#model-profiles
https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/language_models/model_profile.py
"""

from pydantic import BaseModel

__all__ = [
    "ModelProfile",
    "ModelProfileRegistry",
    ]

class ModelProfile(BaseModel):
    """Model profile.
    """

    # --- Input constraints ---

    max_input_tokens: int | None = None
    """Maximum context window (tokens)"""

    image_inputs: bool | None = None
    """Whether image inputs are supported."""
    # TODO: add more detail about formats?

    image_url_inputs: bool | None = None
    """Whether [image URL inputs](https://docs.langchain.com/oss/python/langchain/models#multimodal)
    are supported."""

    pdf_inputs: bool | None = None
    """Whether [PDF inputs](https://docs.langchain.com/oss/python/langchain/models#multimodal)
    are supported."""
    # TODO: add more detail about formats? e.g. bytes or base64

    audio_inputs: bool | None = None
    """Whether [audio inputs](https://docs.langchain.com/oss/python/langchain/models#multimodal)
    are supported."""
    # TODO: add more detail about formats? e.g. bytes or base64

    video_inputs: bool | None = None
    """Whether [video inputs](https://docs.langchain.com/oss/python/langchain/models#multimodal)
    are supported."""
    # TODO: add more detail about formats? e.g. bytes or base64

    image_tool_message: bool | None = None
    """Whether images can be included in tool messages."""

    pdf_tool_message: bool | None = None
    """Whether PDFs can be included in tool messages."""

    # --- Output constraints ---

    max_output_tokens: int | None = None
    """Maximum output tokens"""

    reasoning_output: bool | None = None
    """Whether the model supports [reasoning / chain-of-thought](https://docs.langchain.com/oss/python/langchain/models#reasoning)"""

    image_outputs: bool | None = None
    """Whether [image outputs](https://docs.langchain.com/oss/python/langchain/models#multimodal)
    are supported."""

    audio_outputs: bool | None = None
    """Whether [audio outputs](https://docs.langchain.com/oss/python/langchain/models#multimodal)
    are supported."""

    video_outputs: bool | None = None
    """Whether [video outputs](https://docs.langchain.com/oss/python/langchain/models#multimodal)
    are supported."""

    # --- Tool calling ---
    tool_calling: bool | None = None
    """Whether the model supports [tool calling](https://docs.langchain.com/oss/python/langchain/models#tool-calling)"""

    tool_choice: bool | None = None
    """Whether the model supports [tool choice](https://docs.langchain.com/oss/python/langchain/models#forcing-tool-calls)"""

    # --- Structured output ---
    structured_output: bool | None = None
    """Whether the model supports a native [structured output](https://docs.langchain.com/oss/python/langchain/models#structured-outputs)
    feature"""


ModelProfileRegistry = dict[str, ModelProfile]
"""Registry mapping model identifiers or names to their ModelProfile."""
