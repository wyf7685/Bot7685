import contextlib
import json

from nonebot import logger, require
from nonebot.message import run_postprocessor
from nonebot.utils import escape_tag
from pydantic import ValidationError

local_ns_lookup = {
    "BaseModel.model_validate": "obj",
    "BaseModel.model_validate_json": "json_data",
    "BaseModel.__init__": "data",
    "TypeAdapter.validate_python": "object",
    "TypeAdapter.validate_json": "data",
}


@run_postprocessor
async def catch_error(exception: ValidationError) -> None:
    traceback = exception.__traceback__
    qualname = None

    while (
        traceback is not None
        and (qualname := traceback.tb_frame.f_code.co_qualname) not in local_ns_lookup
    ):
        traceback = traceback.tb_next

    if traceback is None or qualname is None:
        return

    local_ns = traceback.tb_frame.f_locals
    var_name = local_ns_lookup[qualname]
    if var_name not in local_ns:
        logger.warning(
            f"Failed to inspect ValidationError: variable '{var_name}' not found"
            f" in local namespace of function '{qualname}'"
        )
        return

    var_value = local_ns[var_name]
    if isinstance(var_value, str | bytes):
        with contextlib.suppress(json.JSONDecodeError):
            var_value = json.loads(var_value)

    require("src.plugins.patch_event")
    from src.plugins.patch_event.highlight import Highlight

    colored = Highlight.apply(var_value)
    logger.opt(colors=True).error(
        f"ValidationError in function '{qualname}':\n"
        f"Input data:\n{colored}\n"
        f"Error details:\n{escape_tag(repr(exception))}"
    )
