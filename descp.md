The main fix
Stop multiplying the manifest total by 1.5–2.5 unless your package table is based on raw wheel sizes. Right now it is not.
So this part should change:
# Current
dep_low_mb = dep_total_mb * VENV_EXPANSION_FACTOR_LOW
dep_high_mb = dep_total_mb * VENV_EXPANSION_FACTOR_HIGH
to something closer to:
# Better if _package_size() already means installed footprint
dep_low_mb = dep_total_mb * 0.9
dep_high_mb = dep_total_mb * 1.15
Or even:
dep_low_mb = dep_total_mb
dep_high_mb = dep_total_mb * 1.1
if your package-size table is already conservative.
Better architecture
Use this structure instead:
Tracked repo size = exact GitHub blob sum
Installed footprint = sum of unique runtime deps only
Optional/dev deps = separate category
Hidden downloads = separate category
Uncertainty range = small band around the total, not a blanket multiplier
Minimal dedupe fix
Collect package names once, across all manifests:
all_packages = {}
for manifest_path in manifests:
    content = _fetch_file_content(owner, repo, manifest_path)
    if not content:
        continue

    est_mb, breakdown = _estimate_install_footprint_from_manifest(manifest_path, content)
    # better: modify parser functions to return package names too
Even simpler, change your parsers so they return package names, then dedupe before sizing:
unique_pkgs = []
seen = set()

for pkg in parsed_packages:
    pkg = _normalize_pkg_name(pkg)
    if pkg and pkg not in seen:
        seen.add(pkg)
        unique_pkgs.append(pkg)

total = sum(_package_size(pkg) for pkg in unique_pkgs)
What I would change first
If you only change two things, do these:
Remove or greatly reduce the 1.5–2.5x multiplier.
Deduplicate dependencies across all manifests before summing sizes.
That will usually fix the “now it overestimates” problem immediately.
One more issue
Your comment says:
“raw wheel sums underestimate real venv size by 1.5–2.5x”
But your estimator does not compute raw wheel sums. It already uses installed-footprint guesses from _KNOWN_PACKAGE_SIZES_MB. So the comment and the math do not match.