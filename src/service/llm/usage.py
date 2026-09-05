import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class CompletionTokensDetails:
    accepted_prediction_tokens: int = 0
    audio_tokens: int = 0
    reasoning_tokens: int = 0
    rejected_prediction_tokens: int = 0

    def __post_init__(self) -> None:
        counts = (
            self.accepted_prediction_tokens,
            self.audio_tokens,
            self.reasoning_tokens,
            self.rejected_prediction_tokens,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in counts
        ):
            raise TypeError("token counts must be integers")
        if any(value < 0 for value in counts):
            raise ValueError("token counts must not be negative")

    def __add__(self, other: CompletionTokensDetails) -> CompletionTokensDetails:
        return CompletionTokensDetails(
            accepted_prediction_tokens=self.accepted_prediction_tokens
            + other.accepted_prediction_tokens,
            audio_tokens=self.audio_tokens + other.audio_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            rejected_prediction_tokens=self.rejected_prediction_tokens
            + other.rejected_prediction_tokens,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class PromptTokensDetails:
    audio_tokens: int = 0
    cached_tokens: int = 0
    cache_creation_tokens: int = 0

    def __post_init__(self) -> None:
        counts = (self.audio_tokens, self.cached_tokens, self.cache_creation_tokens)
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in counts
        ):
            raise TypeError("token counts must be integers")
        if any(value < 0 for value in counts):
            raise ValueError("token counts must not be negative")

    def __add__(self, other: PromptTokensDetails) -> PromptTokensDetails:
        return PromptTokensDetails(
            audio_tokens=self.audio_tokens + other.audio_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            cache_creation_tokens=self.cache_creation_tokens
            + other.cache_creation_tokens,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class TokenUsage:
    completion_tokens: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0
    completion_tokens_details: CompletionTokensDetails = dataclasses.field(
        default_factory=CompletionTokensDetails
    )
    prompt_tokens_details: PromptTokensDetails = dataclasses.field(
        default_factory=PromptTokensDetails
    )

    def __post_init__(self) -> None:
        counts = (self.completion_tokens, self.prompt_tokens, self.total_tokens)
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in counts
        ):
            raise TypeError("token counts must be integers")
        if any(value < 0 for value in counts):
            raise ValueError("token counts must not be negative")
        if not isinstance(self.completion_tokens_details, CompletionTokensDetails):
            raise TypeError("completion_tokens_details has an invalid type")
        if not isinstance(self.prompt_tokens_details, PromptTokensDetails):
            raise TypeError("prompt_tokens_details has an invalid type")

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            completion_tokens_details=self.completion_tokens_details
            + other.completion_tokens_details,
            prompt_tokens_details=self.prompt_tokens_details
            + other.prompt_tokens_details,
        )
