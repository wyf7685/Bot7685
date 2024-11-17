from . import common, onebot11

processors = {
    None: common.MessageProcessor,
    "OneBot V11": onebot11.MessageProcessor,
}


def get_processor(adapter: str | None) -> common.MessageProcessor:
    return processors.get(adapter, common.MessageProcessor)()
