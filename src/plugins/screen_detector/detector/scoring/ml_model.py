class MLModel:
    def predict(self, features: dict[str, float]) -> float:
        return float(sum(features.values()) / max(len(features), 1))
