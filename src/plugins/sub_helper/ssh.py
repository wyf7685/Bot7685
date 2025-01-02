import paramiko
from nonebot.utils import run_sync

from .config import plugin_config

config = plugin_config.ssh


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
        sftp = self.ssh.open_sftp()
        for fp in config.sub_helper_data.iterdir():
            sftp.put(fp, f"/root/{fp.name}")
        sftp.close()

    def execute_cmd(self, cmd: str) -> None:
        self.ssh.exec_command(cmd)[1].read()

    @classmethod
    @run_sync
    def setup_server(cls, host: str) -> None:
        self = cls(host)
        self.put_files()
        self.execute_cmd("chmod +x /root/executable")
        self.execute_cmd("bash /root/setup.sh")
        self.ssh.close()
