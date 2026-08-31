#!/bin/bash
# Stop macOS prompting for keychain access on every launch.
#
# There are two independent gates on a keychain item, and both must allow the app:
#
#   1. The ACL application list — which binaries may read the item. Handled by
#      `-T` when the item is written.
#   2. The partition list (macOS Sierra and later) — a second check that is NOT
#      set by `-T` and can only be changed by supplying the login password.
#      Until it names the signing identity, macOS prompts even though the ACL
#      already allows the app.
#
# Gate 1 was already fixed by re-writing the items. This script fixes gate 2,
# which is why it needs your password — passing it as `-k` is what authorises
# the change, and it is used only for that.
#
# Both gates key off the signing identity, which is now a stable self-signed
# certificate, so this survives future rebuilds. Run once.
set -uo pipefail

SERVICE="com.berkshire.nexus"
ACCOUNTS=(binance-api-key binance-api-secret ai-provider-api-key alphavantage-api-key)

# Certificate the app is signed with; the partition list is keyed to its hash.
CERT_SHA=$(security find-certificate -c "BerkshireNexus Local Signing" -Z 2>/dev/null \
  | awk '/SHA-1 hash/ {print $NF; exit}')
if [ -z "${CERT_SHA}" ]; then
  echo "找不到签名证书 BerkshireNexus Local Signing" >&2
  exit 1
fi

read -r -s -p "请输入 macOS 登录密码（仅用于修改钥匙串 partition list）: " PASSWORD
echo

failed=0
for account in "${ACCOUNTS[@]}"; do
  if ! security find-generic-password -s "$SERVICE" -a "$account" >/dev/null 2>&1; then
    echo "  跳过 $account（未配置）"
    continue
  fi
  if security set-generic-password-partition-list \
       -s "$SERVICE" -a "$account" \
       -S "apple-tool:,apple:,teamid:${CERT_SHA}" \
       -k "$PASSWORD" >/dev/null 2>&1; then
    echo "  ✓ $account"
  else
    echo "  ✗ $account 失败（密码错误？）"
    failed=1
  fi
done
unset PASSWORD

echo
if [ "$failed" -eq 0 ]; then
  echo "完成。重新打开 App 应该不再弹窗，之后重新构建也不会。"
else
  echo "部分条目未更新，请确认密码后重试。" >&2
  exit 1
fi
