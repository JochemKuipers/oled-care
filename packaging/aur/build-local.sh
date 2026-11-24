#!/usr/bin/env bash
# Build an Arch package from the local tree (no GitHub tag required).
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
aur="$(cd "$(dirname "$0")" && pwd)"
pkgver="$(sed -n 's/^version = "\(.*\)"/\1/p' "$root/pyproject.toml" | head -1)"
pkgname=oled-care
tarball="$aur/$pkgname-$pkgver.tar.gz"

cd "$root"
if git rev-parse HEAD >/dev/null 2>&1; then
  git archive --format=tar.gz --prefix="$pkgname-$pkgver/" -o "$tarball" HEAD
else
  # No commits yet — pack the working tree.
  tar --exclude='.git' --exclude='.venv' --exclude='packaging/aur/*.pkg.tar.*' \
      --exclude='packaging/aur/PKGBUILD.local' --exclude='packaging/aur/*.tar.gz' \
      --exclude='*/__pycache__' --exclude='*.egg-info' \
      -czf "$tarball" --transform "s,^,${pkgname}-${pkgver}/," .
fi

cd "$aur"
# Point source at the local archive and compute checksum.
sed -e "s|^pkgver=.*|pkgver=$pkgver|" \
    -e "s|^source=.*|source=(\"$pkgname-$pkgver.tar.gz\")|" \
    -e "s|^sha256sums=.*|sha256sums=('$(sha256sum "$tarball" | awk '{print $1}')')|" \
    PKGBUILD > PKGBUILD.local

# -d: skip pacman dep install (use when python-pywayland isn't installed yet;
#     pass -s yourself if you want makepkg to install depends).
makepkg -f -d -p PKGBUILD.local "$@"
echo "Built packages in $aur:"
ls -1 "$aur"/"$pkgname"-*.pkg.tar.* 2>/dev/null || true
