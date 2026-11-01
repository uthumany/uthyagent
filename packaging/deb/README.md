# Debian packaging status

`control` and `uthyagent.desktop` are metadata templates only. There is no complete `debian/` source package, install map, post-install script, icon installation rule, dependency-resolution test, maintainer contact, reproducible `.deb` build, upgrade/uninstall test, or Zorin OS verification.

`maintainers@example.invalid` is intentionally a non-deliverable placeholder and must be replaced by the owner before any package is produced. The current metadata lists GTK4 rather than GTK3 to avoid contradicting the app, but that is not evidence that the package works.

Do not publish or install a package from this directory. Before a Debian-family package can be called supported, complete and test the runtime dependencies, bundle the app and logo into the correct system locations, ensure the launcher resolves its icon, build in a clean environment, install and remove it on the target distro, and publish checksums and provenance.
