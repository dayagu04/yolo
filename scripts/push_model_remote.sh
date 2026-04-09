#!/usr/bin/env bash
# 将训练得到的权重（及可选 metrics）同步到远程目录。权重在 .gitignore 中，请用 rsync/scp，勿指望普通 git push。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# 未设置 REMOTE 时，可读仓库根目录 .deploy_remote（单行 user@host:/path，# 开头为注释）
if [[ -z "${REMOTE:-}" && -f "$REPO_ROOT/.deploy_remote" ]]; then
  REMOTE="$(grep -v '^\s*#' "$REPO_ROOT/.deploy_remote" | grep -v '^\s*$' | head -1 | tr -d '\r\n')"
fi

DEFAULT_WEIGHT="runs/detect/runs/person_best_config/weights/best.pt"
WEIGHT="${WEIGHT:-$DEFAULT_WEIGHT}"

if [[ ! -f "$WEIGHT" ]]; then
  echo "未找到权重: $WEIGHT"
  echo "请先完成训练: python3 scripts/train.py"
  echo "或指定: WEIGHT=/path/to/best.pt $0"
  exit 1
fi

if [[ -z "${REMOTE:-}" ]]; then
  echo "用法: REMOTE=user@host:/远程/目录 $0"
  echo "可选: WEIGHT=相对或绝对路径"
  echo "示例: REMOTE=deploy@192.168.1.10:/opt/models/person $0"
  exit 1
fi

RUN_DIR="$(cd "$(dirname "$WEIGHT")/.." && pwd)"
EXTRA=()
[[ -f "$RUN_DIR/results.csv" ]] && EXTRA+=("$RUN_DIR/results.csv")

echo "同步: $WEIGHT -> ${REMOTE%/}/"
rsync -avz --progress -e ssh "$WEIGHT" "${REMOTE%/}/"
if ((${#EXTRA[@]})); then
  rsync -avz --progress -e ssh "${EXTRA[@]}" "${REMOTE%/}/"
fi

echo "完成。远程加载示例: YOLO('.../best.pt') 或复制到服务配置的路径。"
