from .._backend import EndpointBackend, EndpointProtocol
from ..config import EndpointConfig


def create_backend(endpoint: EndpointConfig) -> EndpointBackend:
    match endpoint.protocol:
        case EndpointProtocol.OPENAI_COMPLETIONS:
            from .completions import OpenAICompletionBackend

            return OpenAICompletionBackend(endpoint)
        case EndpointProtocol.OPENAI_RESPONSES:
            from .responses import OpenAIResponsesBackend

            return OpenAIResponsesBackend(endpoint)
        case EndpointProtocol.ANTHROPIC_MESSAGES:
            from .messages import AnthropicMessagesBackend

            return AnthropicMessagesBackend(endpoint)


__all__ = ["create_backend"]
