from typing import final

import paramiko
from nonebot import logger
from nonebot.utils import run_sync

from .config import plugin_config

config = plugin_config.ssh


@final
class SSHClient:
    def __init__(self, host: str) -> None:
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = paramiko.RSAKey.from_private_key_file(config.private_key)
        self.ssh.connect(
            hostname=host,
            port=config.port,
            username=config.username,
            pkey=private_key,
        )

    def put_files(self) -> None:
        (config.sub_helper_data / config.update_file).write_text(
            str(eval(config.update_eval))  # noqa: S307
        )
        with self.ssh.open_sftp() as sftp:
            for fp in config.sub_helper_data.iterdir():
                logger.info(f"put file: {fp.name}")
                sftp.put(fp, f"/root/{fp.name}")

    def execute_cmd(self, cmd: str) -> str:
        return self.ssh.exec_command(cmd)[1].read().decode("utf-8")

    @classmethod
    @run_sync
    def setup_server(cls, host: str) -> None:
        self = cls(host)
        self.put_files()
        logger.info("put files done")
        logger.info("\n" + self.execute_cmd("bash /root/setup.sh"))
        self.ssh.close()
