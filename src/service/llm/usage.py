import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class CompletionTokensDetails:
    accepted_prediction_tokens: int = 0
    audio_tokens: int = 0
    reasoning_tokens: int = 0
    rejected_prediction_tokens: int = 0

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

    def __add__(self, other: PromptTokensDetails) -> PromptTokensDetails:
        return PromptTokensDetails(
            audio_tokens=self.audio_tokens + other.audio_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
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
