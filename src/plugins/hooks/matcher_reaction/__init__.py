"""为触发的匹配器添加 reaction, 并缓存异常供事后查看。

匹配器执行期间贴 [咖啡], 结束后贴 [庆祝]/[发抖]。
异常记录以消息 ID 为键缓存; 对该消息贴 [睁眼] 即可拉取,
traceback 渲染为高亮图片后以合并转发发出。
"""

import contextlib

from . import reaction as reaction

with contextlib.suppress(ImportError, RuntimeError):
    from . import forward as forward
