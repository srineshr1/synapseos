#!/usr/bin/env bash
# shellcheck disable=SC2034

iso_name="synapseos"
iso_label="SYNAPSEOS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="SynapseOS <https://github.com/SynapseOs>"
iso_application="SynapseOS Live/Rescue DVD"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="synapseos"
buildmodes=('iso')
bootmodes=('bios.syslinux'
           'uefi.grub')
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/root"]="0:0:750"
  ["/root/customize_airootfs.sh"]="0:0:755"
  ["/root/.automated_script.sh"]="0:0:755"
  ["/root/.gnupg"]="0:0:700"
  ["/usr/local/bin/choose-mirror"]="0:0:755"
  ["/usr/local/bin/Installation_guide"]="0:0:755"
  ["/usr/local/bin/livecd-sound"]="0:0:755"
  ["/usr/bin/synapseos-installer"]="0:0:755"
  ["/usr/bin/synapseos-logs"]="0:0:755"
  ["/usr/bin/synapseos-safe-graphics"]="0:0:755"
  ["/usr/bin/synapseos-plasma"]="0:0:755"
  ["/usr/bin/synapseos-apply-dock"]="0:0:755"
  ["/usr/bin/synapseos-apply-chrome"]="0:0:755"
  ["/usr/bin/synapseos-core"]="0:0:755"
  ["/usr/bin/synapseos-overlay"]="0:0:755"
  ["/usr/bin/synapseos-mcp"]="0:0:755"
  ["/usr/bin/synapsectl"]="0:0:755"
  ["/usr/bin/synapseos-check-desktop"]="0:0:755"
  ["/usr/share/synapseos/prepare.sh"]="0:0:755"
  ["/usr/share/synapseos/postinstall.sh"]="0:0:755"
  ["/usr/share/synapseos/inject-plymouth.sh"]="0:0:755"
)