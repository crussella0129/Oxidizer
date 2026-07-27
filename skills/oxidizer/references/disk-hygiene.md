# Disk hygiene

Rust builds are large. This matters to Oxidizer specifically because
`oxidize diagnose` shells out to `cargo check` and `cargo clippy`, so using this
skill on a Cargo project *writes into that project's `target/`*. The skill is a
contributor to the problem, not a neutral observer of it.

Measured on this repository's own MCP server — a single binary with about
thirty dependencies:

| | Size |
|---|---|
| `target/` total | 785.2 MiB / 1,508 files |
| `target/debug/deps` | 437.4 MiB |
| `target/debug/incremental` | 181.1 MiB |
| `target/debug/build` | 109.1 MiB |
| `~/.cargo/registry` | 55.8 MiB |
| The entire mirrored Rust canon, for comparison | 39.6 MiB |

The build tree is nearly twenty times the size of the corpus. (`du` will report
larger figures — 56 MiB for the corpus — because it counts allocated blocks, and
the corpus is 5,263 small files. The numbers above are actual bytes, which is
what `cargo clean --dry-run` also reports.)

## The rule is conditional, not periodic

`cargo clean` is destructive to build speed. It removes `incremental/`, which is
the state that makes the next edit-compile cycle fast rather than a cold
rebuild. Advice to "run `cargo clean` regularly" is therefore wrong as stated —
followed literally on a project someone is actively iterating on, it converts
every build into a full one.

**Clean when the artifacts have stopped earning their disk:**

- You have finished with a project and are moving on.
- You switched toolchains or editions — stale artifacts from another `rustc` are
  dead weight the new one cannot use.
- You ran a one-off `--release` build and only needed the binary.
- You are actually short of disk, or working in an ephemeral environment with a
  fixed allowance.
- A dependency bump invalidated most of the tree anyway.

**Do not clean when:**

- The user is mid-iteration and will build again in a minute.
- You are about to run `diagnose` again on the same project — you would pay a
  full rebuild to save space you are about to re-spend.

## Prefer a targeted clean

Removing the whole tree is rarely what is wanted. `cargo clean` takes options
that cost far less:

```bash
cargo clean --dry-run              # what would go, and how much — always start here
cargo clean --release              # drop release artifacts, keep the dev cycle fast
cargo clean --profile dev          # the inverse: keep the release binary
cargo clean -p <crate>             # one package in a workspace
cargo clean --doc                  # just target/doc
cargo clean                        # everything, including incremental state
```

`--dry-run` reports an exact file count and total before anything is removed. On
a tree you did not create, run it first — the number is often much larger or much
smaller than expected, and it makes the decision for you.

## Ask before cleaning someone else's tree

Removing build artifacts is not dangerous — cargo will regenerate them — but it
is not free either, and it is the user's machine and the user's time. Deleting a
790 MiB tree that took four minutes to build, without being asked, is a bad
trade to make on someone's behalf.

Report the size and the command; let the user run it. `oxidize disk` exists to
make that a one-liner. It never deletes anything itself, by design.

## What Oxidizer itself costs, and cleans up

- **Single-file `diagnose`** compiles into a `tempfile.TemporaryDirectory()` that
  is removed when the command exits. It leaves nothing behind.
- **Project `diagnose`** runs `cargo check` in the user's project, which writes
  to `target/`. `check` artifacts are considerably smaller than a full `build`,
  but they accumulate.
- **`mirror.py`** removes each source directory before rebuilding it, so
  re-running it replaces the corpus rather than growing it. The corpus is ~56 MiB
  and gitignored.
- **The MCP server**, once built for release, does not need its debug tree. Copy
  the binary out and `cargo clean --profile dev`.

## Beyond `target/`

`~/.cargo/registry` caches downloaded crate sources and `.crate` archives, and
grows monotonically — nothing prunes it. `cargo clean` does not touch it. The
`cargo-cache` subcommand (`cargo install cargo-cache`, then `cargo cache --autoclean`)
prunes it safely; `cargo-sweep` removes artifacts older than a given age across
many projects at once. Neither is installed by default, so suggest rather than
assume.
