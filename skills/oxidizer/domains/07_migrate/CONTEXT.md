# Layer 2 — 07_migrate: port from C, C++, or another language

The user has working code in another language and wants the Rust version.

## Inputs

| What | Where from | Load when |
|---|---|---|
| Idiom translation | `oxidize search "<construct>" --source crp-phrasebook` then `show` | C or C++ source |
| The Rust concept behind it | `--source book` | The mapping is not mechanical |
| FFI and layout | `--source nomicon` | Interoperating rather than rewriting |
| Ownership rules | `--source reference` | The original relies on aliasing |

## Process

1. For C++, start with the phrasebook: `oxidize search "<construct>"
   --source crp-phrasebook`. It is organised around exactly this task and shows
   both languages side by side.
2. Translate the *intent*, not the syntax. The literal transliteration of a C++
   pattern is usually the one that fights the borrow checker hardest.
3. Where the original relies on something Rust forbids — mutable aliasing,
   shared mutation without synchronisation, inheritance — name the Rust design
   that replaces it rather than reaching for `unsafe` to preserve the shape.
4. Compile the result (`oxidize diagnose`) before presenting it.

## Common mappings

| C++ | Rust | Note |
|---|---|---|
| `std::unique_ptr<T>` | `Box<T>` | Direct |
| `std::shared_ptr<T>` | `Rc<T>` / `Arc<T>` | `Arc` only if it crosses threads |
| `std::weak_ptr<T>` | `Weak<T>` | Same cycle-breaking role |
| `std::vector<T>` | `Vec<T>` | Direct |
| `std::string` | `String` / `&str` | Owned vs borrowed is now explicit |
| `std::optional<T>` | `Option<T>` | Rust's is not nullable-by-accident |
| `T*` (nullable) | `Option<&T>` | Same size; no null pointer |
| `T&` | `&T` / `&mut T` | Mutability is now part of the type |
| Virtual base class | `trait` + `dyn Trait` | Composition, not inheritance |
| Template | Generic + trait bounds | Bounds are checked at definition |
| RAII destructor | `Drop` | Cannot be called manually; use `drop()` |
| Copy constructor | `Clone` | Explicit; never implicit |
| Move constructor | Moves are the default | No moved-from state to handle |
| Exception | `Result<T, E>` + `?` | Not an exception; a value |
| `const` method | `&self` | |
| `std::mutex` + data | `Mutex<T>` | Rust puts the data *inside* the lock |

## Design shifts worth stating explicitly

**Inheritance does not port.** An abstract base with virtual methods becomes a
trait; a concrete base with shared state becomes composition plus a trait impl.
Users coming from C++ often try to recreate the hierarchy and stall — say this
early.

**Aliasing is the real constraint.** A C++ object graph where several parents
hold mutable pointers to the same child has no direct Rust equivalent. The
options are `Rc<RefCell<T>>` (runtime-checked, single-threaded), an arena with
indices (usually the better answer for graphs), or restructuring so ownership is
a tree. Indices are underused and worth suggesting.

**Mutex wraps the data.** In C++ the mutex sits beside what it protects and
discipline keeps them together; in Rust `Mutex<T>` makes it impossible to touch
the data without the lock. Port to the Rust shape rather than keeping a bare
mutex and a separate field.

## Porting whole files

Go incrementally: one type or module at a time, compiling as you go. A full-file
translation that produces sixty simultaneous borrow errors helps nobody. If the
user wants to interoperate rather than rewrite, that is FFI — go to `05_unsafe`.

## Outputs

- The Rust version, compiling.
- Where the design had to change, and why — not just what.
- Anything that could not be preserved and what was done instead.

## Hand off

- The port does not compile → `01_diagnose`
- It compiles but reads like C++ → `06_idiom`
- Keeping the C++ and calling into it → `05_unsafe`
