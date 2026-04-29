"""
Alembic 迁移环境配置
从 config.yaml 读取数据库连接信息，自动发现 backend/database.py 中的 ORM 模型
"""
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# 将项目根目录加入 sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.database import Base  # noqa: E402 — 导入所有 ORM 模型的 MetaData

# Alembic Config 对象
config = context.config

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate support
target_metadata = Base.metadata


def _build_db_url() -> str:
    """从 config.yaml 构建数据库连接 URL"""
    import yaml
    cfg_path = ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db = cfg.get("database", {})
    return (
        f"mysql+pymysql://{db['user']}:{db['password']}"
        f"@{db['host']}:{db['port']}/{db['database']}"
        f"?charset={db.get('charset', 'utf8mb4')}"
    )


def run_migrations_offline() -> None:
    """在 'offline' 模式下运行迁移（生成 SQL 脚本）"""
    url = _build_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在 'online' 模式下运行迁移（直接连接数据库）"""
    url = _build_db_url()
    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
