from . import common, onebot11, telegram

processors = {
    None: common.MessageProcessor,
    "OneBot V11": onebot11.MessageProcessor,
    "Telegram": telegram.MessageProcessor,
}


def get_processor(adapter: str | None) -> type[common.MessageProcessor]:
    return processors.get(adapter, common.MessageProcessor)
