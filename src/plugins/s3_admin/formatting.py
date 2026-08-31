from src.service.s3 import S3Config, S3ConfigurationSnapshot


def format_config(config: S3Config) -> str:
    endpoint = config.endpoint_url or "AWS 默认 Endpoint"
    presign_endpoint = config.presign_endpoint_url or endpoint
    prefix = config.key_prefix or "<bucket root>"
    addressing = "path-style" if config.path_style else "virtual-hosted-style"
    token = "已配置" if config.session_token is not None else "未配置"
    return (
        f"Region: {config.region}\n"
        f"Bucket: {config.bucket}\n"
        f"请求 Endpoint: {endpoint}\n"
        f"预签名 Endpoint: {presign_endpoint}\n"
        f"协议: {config.scheme}\n"
        f"寻址: {addressing}\n"
        f"Key 前缀: {prefix}\n"
        f"最大并发: {config.max_concurrency}\n"
        f"请求超时: {float(config.timeout_seconds):g}s\n"
        f"Session Token: {token}"
    )


def format_status(
    snapshot: S3ConfigurationSnapshot,
    *,
    connected: bool | None = None,
) -> str:
    if snapshot.config is None:
        state = "配置文件不可用" if snapshot.load_error else "未配置"
        return f"S3 状态: {state}\nRevision: {snapshot.revision}"
    connection = "未检查" if connected is None else ("可用" if connected else "不可用")
    return (
        f"S3 状态\nRevision: {snapshot.revision}\n连接: {connection}\n\n"
        f"{format_config(snapshot.config)}"
    )


__all__ = ["format_config", "format_status"]
