<div align="center">

# Bot7685

_✨ Bot7685 by wyf7685 ✨_

[![python](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=edb641)](https://www.python.org/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

[![wakatime](https://wakatime.com/badge/user/b097681b-c224-44ec-8e04-e1cf71744655/project/673e4e12-44ca-45d5-9a9f-8eba554c9ecc.svg)](https://wakatime.com/badge/user/b097681b-c224-44ec-8e04-e1cf71744655/project/673e4e12-44ca-45d5-9a9f-8eba554c9ecc)
![works on my machine](https://img.shields.io/badge/works%20on-my%20machine-green)

</div>

## ZSSM 诊断日志

使用同一 `run` 关联输入、图片处理、工具调用、模型请求和最终回复。失败日志保留阶段、
模型别名、调用序号、计数与限制，并记录异常链及代码位置。HTTP 状态错误会记录状态码；
上游提供时，还记录 request ID 和允许记录的错误字段，便于定位 500 的具体原因。

诊断不转储完整请求/响应正文、配置或栈帧局部变量；凭据、URL 和请求中可识别的输入文本
经过脱敏，Pydantic 校验失败仅记录字段位置与错误类型。超长字段以 `...` 结尾，
超过异常链或总长度上限时分别标记 `error_chain=truncated` 或 `diagnostics_truncated=true`。
详细诊断只写日志，用户回复仍使用简短的错误分类提示。
