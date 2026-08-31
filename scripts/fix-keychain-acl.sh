#!/bin/bash
# Reduce keychain prompts for the locally-signed app.
#
# What can and cannot be fixed, measured on this machine:
#
#   * ACL application list — fixable, and already correct: each item names
#     /Applications/BerkshireNexus.app with the requirement
#     `identifier "com.berkshire.nexus" and certificate leaf = H"a9cdc358..."`,
#     pinned to the stable signing certificate.
#
#   * Partition list — NOT fixable for a self-signed build. It accepts only
#     `apple:`, `apple-tool:`, a 10-character Apple Team ID, or a cdhash. This
#     certificate has no Team ID (codesign reports `TeamIdentifier=not set`) and
#     a cdhash changes on every build, so no entry can match. An earlier version
#     of this script wrote the certificate SHA-1 as a `teamid:`, which is not a
#     Team ID and was silently inert — that is why the prompts continued.
#
# So the prompt on first unlock per launch is a property of self-signed code on
# macOS, not a bug we can configure away. The app now caches each secret in
# memory after its first read, so it asks at most once per secret per launch
# instead of once per operation. Only a real Apple Developer ID removes it
# entirely, by giving the partition list a Team ID to trust.
#
# This script still helps after a fresh install or a certificate change: it
# rewrites each item so its ACL names the current app, clearing dead entries
# accumulated from earlier ad-hoc builds.
set -uo pipefail

SERVICE="com.berkshire.nexus"
APP="/Applications/BerkshireNexus.app"
ACCOUNTS=(binance-api-key binance-api-secret ai-provider-api-key alphavantage-api-key)

if [ ! -d "$APP" ]; then
  echo "找不到 $APP，请先安装 App" >&2
  exit 1
fi

echo "重写钥匙串条目的 ACL，使其指向当前已签名的 App。"
echo

for account in "${ACCOUNTS[@]}"; do
  if ! value=$(security find-generic-password -s "$SERVICE" -a "$account" -w 2>/dev/null); then
    echo "  跳过 $account（未配置）"
    continue
  fi
  security delete-generic-password -s "$SERVICE" -a "$account" >/dev/null 2>&1
  security add-generic-password -U -s "$SERVICE" -a "$account" -w "$value" \
    -T "$APP" -T /usr/bin/security
  echo "  ✓ $account"
done

echo
echo "完成。首次启动后每个凭证仍可能弹一次授权——点「始终允许」即可，"
echo "App 会把已读取的凭证缓存在内存中，本次运行内不再重复询问。"
echo "彻底免弹窗需要 Apple Developer ID 签名（自签名证书没有 Team ID）。"
