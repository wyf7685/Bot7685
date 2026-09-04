"""增量分析批次持久化存储 — 滑动窗口架构。

基于 src.service.kv 实现按批次独立存储，使用 uninfo SceneModel 的持久 ID
隔离不同 Bot 和适配器中的同名场景。

KV 键设计：
- 批次索引: incr_batch_index_{scene_persist_id}
- 批次数据: incr_batch_{scene_persist_id}_{batch_id}
- 最后分析消息时间戳: incr_last_ts_{scene_persist_id}
"""

from nonebot.log import logger

from src.service.kv import get_kv_store

from ..domain.incremental import IncrementalBatch, IncrementalIndex


class IncrementalStore:
    """增量分析批次持久化仓储。"""

    INDEX_PREFIX = "incr_batch_index"
    BATCH_PREFIX = "incr_batch"
    LAST_TS_PREFIX = "incr_last_ts"

    def __init__(self) -> None:
        self._raw = get_kv_store()
        self._batch_store = self._raw.with_type(IncrementalBatch)
        self._index_store = self._raw.with_type(list[IncrementalIndex])
        self._last_ts_store = self._raw.with_type(float)

    # ================================================================
    # 键构建
    # ================================================================

    @staticmethod
    def _index_key(scene_persist_id: int) -> str:
        return f"{IncrementalStore.INDEX_PREFIX}_{scene_persist_id}"

    @staticmethod
    def _batch_key(scene_persist_id: int, batch_id: str) -> str:
        return f"{IncrementalStore.BATCH_PREFIX}_{scene_persist_id}_{batch_id}"

    @staticmethod
    def _last_ts_key(scene_persist_id: int) -> str:
        return f"{IncrementalStore.LAST_TS_PREFIX}_{scene_persist_id}"

    # ================================================================
    # 批次索引操作
    # ================================================================

    async def _get_index(self, scene_persist_id: int) -> list[IncrementalIndex]:
        key = self._index_key(scene_persist_id)
        try:
            return await self._index_store.read(key)
        except KeyError:
            return []
        except Exception as e:
            logger.error(f"读取批次索引失败 (Key: {key}): {e}")
            return []

    async def _save_index(
        self,
        scene_persist_id: int,
        index: list[IncrementalIndex],
    ) -> None:
        key = self._index_key(scene_persist_id)
        try:
            await self._index_store.write(key, index)
        except Exception as e:
            logger.error(f"保存批次索引失败 (Key: {key}): {e}")
            raise

    # ================================================================
    # 批次数据操作
    # ================================================================

    async def save_batch(self, batch: IncrementalBatch) -> bool:
        scene_persist_id = batch.scene_persist_id
        batch_key = self._batch_key(scene_persist_id, batch.batch_id)

        try:
            await self._batch_store.write(batch_key, batch)

            index = await self._get_index(scene_persist_id)
            index.append(
                IncrementalIndex(batch_id=batch.batch_id, timestamp=batch.timestamp)
            )
            await self._save_index(scene_persist_id, index)

            logger.debug(
                f"已保存批次 {batch.batch_id[:8]}... "
                f"(scene={scene_persist_id}, 消息数={batch.messages_count})"
            )
        except Exception as e:
            logger.error(
                f"保存批次失败 (scene={scene_persist_id}, "
                f"批次 {batch.batch_id[:8]}...): {e}"
            )
            return False
        else:
            return True

    async def query_batches(
        self,
        scene_persist_id: int,
        window_start: float,
        window_end: float,
    ) -> list[IncrementalBatch]:
        index = await self._get_index(scene_persist_id)

        matching_entries = [
            entry for entry in index if window_start <= entry.timestamp <= window_end
        ]
        matching_entries.sort(key=lambda x: x.timestamp)

        batches: list[IncrementalBatch] = []
        for entry in matching_entries:
            batch_id = entry.batch_id
            if not batch_id:
                continue

            batch_key = self._batch_key(scene_persist_id, batch_id)
            try:
                batch = await self._batch_store.read(batch_key)
                batches.append(batch)
            except KeyError:
                logger.warning(
                    f"批次数据缺失 (scene={scene_persist_id}, 批次 {batch_id[:8]}...)"
                )
            except Exception as e:
                logger.error(
                    f"加载批次数据失败 (scene={scene_persist_id}, "
                    f"批次 {batch_id[:8]}...): {e}"
                )

        logger.debug(
            f"窗口查询完成: scene={scene_persist_id}, "
            f"窗口 [{window_start:.0f}, {window_end:.0f}], "
            f"匹配 {len(batches)}/{len(index)} 个批次"
        )

        return batches

    # ================================================================
    # 最后分析消息时间戳（跨批次去重用）
    # ================================================================

    async def get_last_analyzed_timestamp(self, scene_persist_id: int) -> float:
        key = self._last_ts_key(scene_persist_id)
        try:
            return await self._last_ts_store.read(key)
        except KeyError:
            return 0.0
        except Exception as e:
            logger.error(f"读取最后分析时间戳失败 (Key: {key}): {e}")
            return 0.0

    async def update_last_analyzed_timestamp(
        self,
        scene_persist_id: int,
        timestamp: float,
    ) -> None:
        key = self._last_ts_key(scene_persist_id)
        try:
            await self._last_ts_store.write(key, timestamp)
            logger.debug(
                f"更新最后分析时间戳: scene={scene_persist_id}, ts={timestamp}"
            )
        except Exception as e:
            logger.error(f"更新最后分析时间戳失败 (Key: {key}): {e}")
            raise

    # ================================================================
    # 过期批次清理
    # ================================================================

    async def cleanup_old_batches(
        self,
        scene_persist_id: int,
        before_timestamp: float,
    ) -> int:
        index = await self._get_index(scene_persist_id)
        if not index:
            return 0

        expired: list[IncrementalIndex] = []
        retained: list[IncrementalIndex] = []
        for entry in index:
            if entry.timestamp < before_timestamp:
                expired.append(entry)
            else:
                retained.append(entry)

        if not expired:
            return 0

        deleted_count = 0
        for entry in expired:
            batch_id = entry.batch_id
            if not batch_id:
                continue
            batch_key = self._batch_key(scene_persist_id, batch_id)
            try:
                await self._raw.delete(batch_key)
                deleted_count += 1
            except Exception as e:
                logger.error(
                    f"删除过期批次失败 (scene={scene_persist_id}, "
                    f"批次 {batch_id[:8]}...): {e}"
                )

        await self._save_index(scene_persist_id, retained)

        logger.info(
            f"清理过期批次: scene={scene_persist_id}, "
            f"删除 {deleted_count} 个, 保留 {len(retained)} 个"
        )

        return deleted_count

    # ================================================================
    # 状态查询
    # ================================================================

    async def get_batch_count(self, scene_persist_id: int) -> int:
        index = await self._get_index(scene_persist_id)
        return len(index)

    async def get_all_batch_summaries(
        self,
        scene_persist_id: int,
    ) -> list[IncrementalIndex]:
        index = await self._get_index(scene_persist_id)
        index.sort(key=lambda x: x.timestamp)
        return index
