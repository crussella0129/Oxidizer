# Layer 2 — 04_spec: is this legal, what is guaranteed

The user is asking a normative question. They want to know what the language
promises, not what usually happens.

## Inputs

| What | Where from | Load when |
|---|---|---|
| The normative text | `oxidize search "<topic>" --source reference` then `show` | Always |
| Edition differences | `--source edition-guide` | Behaviour depends on edition |
| Unsafe-adjacent guarantees | `--source nomicon` | The question touches UB or representation |

## Process

1. `oxidize search "<topic>" --source reference`, then `show` the page — often
   with `--section` to reach the exact rule, since Reference pages are long.
2. Quote the normative sentence. Paraphrasing a specification is how guarantees
   get accidentally widened.
3. Distinguish, explicitly, between:
   - **guaranteed** — the Reference states it; you can rely on it
   - **implementation-defined** — true of current rustc, not promised
   - **unspecified** — do not rely on it, even if it is stable today
   - **undefined behaviour** — the program is invalid; see `05_unsafe`
4. If the Reference does not answer it, say so. "The Reference doesn't specify
   this" is a legitimate and useful answer, and much better than inferring a
   guarantee that does not exist.

## Questions that land here

Drop order and destructor timing. Struct layout and `repr`. Integer overflow
behaviour in debug vs release. Coercion sites and where auto-deref applies.
Operator precedence and associativity. Trait coherence and the orphan rule.
Const evaluation limits. Whether a lifetime is elided and to what. Temporary
lifetime extension. What edition changed a given behaviour.

## Caution

Layout is the one people get wrong most. `#[repr(Rust)]` guarantees essentially
nothing about field order, size, or padding — it is explicitly allowed to change
between compilations. Anything relying on layout needs `#[repr(C)]` or
`#[repr(transparent)]`, and that belongs to `05_unsafe`.

Similarly, integer overflow is *not* undefined behaviour in Rust: it panics in
debug and wraps in release. Both are defined; relying on either without saying
which profile you mean is the mistake.

## Outputs

- A direct yes/no/it-depends.
- The quoted normative text plus its Reference URL.
- An explicit label: guaranteed, implementation-defined, unspecified, or UB.
- If edition-dependent, which editions differ and how.

## Hand off

- The answer is "that's UB" → `05_unsafe`
- They wanted intuition rather than the rule → `02_learn`
- It is legal but a bad idea → `06_idiom`
