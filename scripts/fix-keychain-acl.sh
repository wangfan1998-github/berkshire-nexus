#!/bin/bash
# Re-grant keychain access to the signed app.
#
# The credential entries were created while the app was still ad-hoc signed, so
# their ACLs reference a signing identity that no longer exists. The app now uses
# a stable certificate, but the old ACLs do not know about it — which is why
# macOS prompts once per entry on every launch.
#
# This reads each value once (you will be asked to allow that), then rewrites it
# with the current app explicitly in the ACL. Because the signing identity is now
# stable, the grant survives future rebuilds — this only needs running once.
set -euo pipefail

SERVICE="com.berkshire.nexus"
APP="/Applications/BerkshireNexus.app"
ACCOUNTS=(binance-api-key binance-api-secret ai-provider-api-key alphavantage-api-key)

if [ ! -d "$APP" ]; then
  echo "找不到 $APP，请先安装 App" >&2
  exit 1
fi

echo "将为以下条目重新授权（每条弹一次「允许」，之后不再弹）："
printf '  - %s\n' "${ACCOUNTS[@]}"
echo

for account in "${ACCOUNTS[@]}"; do
  if ! value=$(security find-generic-password -s "$SERVICE" -a "$account" -w 2>/dev/null); then
    echo "  跳过 $account（未配置）"
    continue
  fi
  security delete-generic-password -s "$SERVICE" -a "$account" >/dev/null 2>&1 || true
  # -T grants that binary access without a prompt; -U updates in place.
  security add-generic-password -U -s "$SERVICE" -a "$account" -w "$value" \
    -T "$APP" -T /usr/bin/security
  echo "  ✓ $account 已重新授权"
done

echo
echo "完成。下次打开 App 不应再反复弹窗。"
echo "以后重新构建 App 无需重跑本脚本——签名身份已固定。"
