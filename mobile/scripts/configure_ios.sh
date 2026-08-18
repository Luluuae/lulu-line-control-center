#!/usr/bin/env bash
set -euo pipefail

plist="ios/App/App/Info.plist"
if [[ ! -f "$plist" ]]; then
  echo "Missing generated iOS Info.plist" >&2
  exit 1
fi

set_or_add() {
  local key="$1" type="$2" value="$3"
  /usr/libexec/PlistBuddy -c "Set :$key $value" "$plist" 2>/dev/null ||
    /usr/libexec/PlistBuddy -c "Add :$key $type $value" "$plist"
}

set_or_add CFBundleDisplayName string "Lulu Line Control Center"
set_or_add ITSAppUsesNonExemptEncryption bool false
set_or_add NSCameraUsageDescription string "Camera access is used only when an authorised user captures a business document for upload."
set_or_add NSPhotoLibraryUsageDescription string "Photo access is used only when an authorised user selects a business document for upload."

/usr/libexec/PlistBuddy -c "Delete :NSAppTransportSecurity" "$plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity dict" "$plist"
/usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity:NSAllowsArbitraryLoads bool false" "$plist"
/usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity:NSAllowsLocalNetworking bool false" "$plist"

plutil -lint "$plist"
